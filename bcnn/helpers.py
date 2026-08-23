from pathlib import Path
from typing import Protocol, runtime_checkable
import json
from tqdm import tqdm
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from utils.color import Font


@runtime_checkable
class SupportsUpdateGradient(Protocol):
    '''
    This helps make type checking happy when using update_gradient() on the BCNN modules.
    '''
    def update_gradient(self) -> None:
        ...


def train_val(
    model: nn.Module,
    train_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    val_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    loss_fn: nn.Module, 
    optimizer: torch.optim.Optimizer, 
    device: torch.device, 
    cfg: dict[str, str | int | float], 
    output_dir: Path,
    ) -> tuple[dict[str, np.ndarray], float]:
    '''
    Train and validation loop.
    ## Inputs
    - model `nn.Module`: the model to train
    - train_loader `DataLoader`: dataloader for training set
    - val_loader `DataLoader`: dataloader for validation set
    - loss_fn `nn.Module`: loss function
    - optimizer `torch.optim.Optimizer`: optimizer
    - device `torch.device`: device to train on
    - cfg `dict`: config dict for training
    - output_dir `Path`: directory to save the best model and training history
    ## Outputs
    - history `dict[str, np.ndarray]`: dict containing training and validation loss and accuracy history
    - best_val_loss `float`: best validation loss achieved during training
    '''

    # initialize history and best state
    max_epochs = int(cfg["epochs"])
    history = {
        "train_loss": np.full((max_epochs,), np.nan),
        "train_acc": np.full((max_epochs,), np.nan),
        "val_loss": np.full((max_epochs,), np.nan),
        "val_acc": np.full((max_epochs,), np.nan),
        }
    best_val_loss = float("inf")

    # initialize patience
    patience = int(cfg.get("patience", 10))
    min_delta = float(cfg.get("min_delta", 0.001))

    # train the model
    model.train()

    valid_epochs = 0
    for epoch in tqdm(range(1, max_epochs + 1), desc="Training"):
        model.train()
        epoch_loss, epoch_corr = 0.0, 0
        for inputs, targets in tqdm(train_loader, desc=f"Epoch {epoch}/{cfg['epochs']} - Training", leave=False, dynamic_ncols=True):
            inputs, targets = inputs.to(device), targets.to(device)
            # zero grad
            optimizer.zero_grad()

            # forward
            out, _ = model(inputs)
            loss = loss_fn(out, targets)

            # backward
            loss.backward()
            for module in model.modules():
                if isinstance(module, SupportsUpdateGradient):
                    module.update_gradient()
            optimizer.step()

            batch_size = inputs.size(0)
            epoch_loss += loss.item() * batch_size
            epoch_corr += (out.argmax(dim=1) == targets.argmax(dim=1)).sum().item()

        average_loss = epoch_loss / len(train_loader.dataset) # pyright: ignore[reportArgumentType]
        accuracy = epoch_corr / len(train_loader.dataset) # pyright: ignore[reportArgumentType]

        # validation
        val_loss, val_corr = 0.0, 0
        with torch.no_grad():
            for inputs, targets in tqdm(val_loader, desc=f"Epoch {epoch}/{cfg['epochs']} - Validation", leave=False, dynamic_ncols=True):
                inputs, targets = inputs.to(device), targets.to(device)
                out, _ = model(inputs)
                loss = loss_fn(out, targets)

                batch_size = inputs.size(0)
                val_loss += loss.item() * batch_size
                val_corr += (out.argmax(dim=1) == targets.argmax(dim=1)).sum().item()

        average_val_loss = val_loss / len(val_loader.dataset) # pyright: ignore[reportArgumentType]
        val_accuracy = val_corr / len(val_loader.dataset) # pyright: ignore[reportArgumentType]

        # update history
        history["train_loss"][epoch - 1] = average_loss
        history["train_acc"][epoch - 1] = accuracy
        history["val_loss"][epoch - 1] = average_val_loss
        history["val_acc"][epoch - 1] = val_accuracy

        valid_epochs = epoch

        if average_val_loss + min_delta < best_val_loss:
            best_val_loss = average_val_loss
            torch.save(model.state_dict(), output_dir / "best_model.pt")
        else:
            patience -= 1
            if patience == 0:
                tqdm.write(f"{Font.WARNING}Early stopping at epoch {epoch} with best val loss {best_val_loss:.6f}{Font.ENDC}")
                break

    for key in history:
        history[key] = history[key][:valid_epochs]

    return history, best_val_loss

def test(
    model: nn.Module, 
    test_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    loss_fn: nn.Module, 
    device: torch.device
    ) -> tuple[float, float]:
    '''
    Test loop.
    ## Inputs
    - model `nn.Module`: the model to test
    - test_loader `DataLoader`: dataloader for test set
    - loss_fn `nn.Module`: loss function
    - device `torch.device`: device to test on
    ## Outputs
    - test_loss `float`: average test loss
    - test_acc `float`: average test accuracy
    '''
    # test the model
    model.eval()

    test_loss, test_corr = 0.0, 0.0
    with torch.no_grad():
        for inputs, targets in tqdm(test_loader, desc="Testing", leave=False, dynamic_ncols=True):
            inputs, targets = inputs.to(device), targets.to(device)

            out, _ = model(inputs)
            loss = loss_fn(out, targets)
            
            batch_size = inputs.size(0)
            test_loss += loss.item() * batch_size
            test_corr += (out.argmax(dim=1) == targets.argmax(dim=1)).sum().item()

        test_loss /= len(test_loader.dataset) # pyright: ignore[reportArgumentType]
        test_acc = 100 * test_corr / len(test_loader.dataset) # pyright: ignore[reportArgumentType]

    return test_loss, test_acc

def saver(
    history: dict[str, np.ndarray],
    output_dir: Path, 
    best_val_loss: float, 
    test_loss: float, 
    test_acc: float, 
    cfg: dict[str, str | int | float], 
    lr: float | None = None,
    ) -> None:
    '''
    Save the training history and best model.
    ## Inputs
    - history `dict[str, np.ndarray]`: dict containing training loss, validation loss, and accuracy history
    - output_dir `Path`: directory to save the best model and training history
    - best_val_loss `float`: best validation loss achieved during training
    - test_loss `float`: test loss achieved during testing
    - test_acc `float`: test accuracy achieved during testing
    - cfg `dict`: config dict for training
    - lr `float | None` (default = `None`): current learning rate, if sweepning
    ## Outputs
    - None (saves the history and best model to the output directory)
    '''
    # write history
    with open(output_dir / "report.txt", "w", encoding="utf-8") as handle:
        handle.write(f"epochs: {cfg['epochs']}\n")
        handle.write(f"batch_size: {cfg['batch_size']}\n")
        if lr is not None:
            handle.write(f"lr: {lr}\n")
        else:
            handle.write(f"lr: {cfg['lr']}\n")
        handle.write(f"best_val_loss: {best_val_loss:.6f}\n")
        handle.write(f"test_loss: {test_loss:.6f}\n")
        handle.write(f"test_acc: {test_acc:.4f}%\n")

    # convert numpy arrays to lists for json serialization
    history["train_loss"] = history["train_loss"].tolist()
    history["train_acc"] = history["train_acc"].tolist()
    history["val_loss"] = history["val_loss"].tolist()
    history["val_acc"] = history["val_acc"].tolist()

    # save history as json
    with open(output_dir / "history.json", "w", encoding="utf-8") as handle:
        json.dump(history, handle, indent=2)

    plt.figure(figsize=(10, 4))
    plt.plot(history["train_loss"], label="train loss")
    plt.plot(history["val_loss"], label="val loss")
    plt.xlabel("epoch")
    plt.ylabel("loss")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "loss_curve.png")
    plt.close()

    plt.figure(figsize=(10, 4))
    plt.plot(history["train_acc"], label="train acc")
    plt.plot(history["val_acc"], label="val acc")
    plt.xlabel("epoch")
    plt.ylabel("accuracy")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "accuracy_curve.png")
    plt.close()

def examples(
    model: nn.Module, 
    test_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    output_dir: Path, 
    device: torch.device
    ) -> None:
    '''
    Test loop.
    ## Inputs
    - model `nn.Module`: the model to test
    - test_loader `DataLoader`: dataloader for test set
    - output_dir `Path`: directory to save test results
    - device `torch.device`: device to test on
    ## Outputs
    - None (saves test results to the output directory)
    '''
    # save images of outputs and intermediate layers
    model.eval()
    with torch.no_grad():
        for inputs, targets in test_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            out, layers_out = model(inputs)
            break

    # save examples
    torch.save({
        "inputs": inputs.cpu(),    # pyright: ignore[reportPossiblyUnboundVariable]
        "targets": targets.cpu(),  # pyright: ignore[reportPossiblyUnboundVariable]
        "out": out.cpu(),          # pyright: ignore[reportPossiblyUnboundVariable]
        "layers_out": [layer.cpu() for layer in layers_out],  # pyright: ignore[reportPossiblyUnboundVariable]
        }, output_dir / "examples.pt")

    # save images
    output_dir = output_dir / "imgs"
    output_dir.mkdir(parents=True, exist_ok=True)
    layers = ['Layer 1', 'Layer 2', 'Layer 3', 'Pooled Output']
    for i, (input_img, target, output) in tqdm(enumerate(zip(inputs, targets, out)), total=len(inputs)): # pyright: ignore[reportPossiblyUnboundVariable]
        fig, axes = plt.subplots(1, 5, figsize=(18, 5))
        input_img = input_img.cpu().permute(1, 2, 0)  # CxHxW to HxWxC
        axes[0].imshow((input_img - input_img.min()) / (input_img.max() - input_img.min()), cmap="gray")
        axes[0].set_title(f"Input")
        axes[0].axis("off")
        for j in range(len(layers)):
            axes[j + 1].imshow(layers_out[j][i].cpu().squeeze(0), cmap="gray") # pyright: ignore[reportPossiblyUnboundVariable]
            axes[j + 1].set_title(f"{layers[j]}")
            axes[j + 1].axis("off")
        fig.suptitle(f"Target: {target.argmax().item()} - Output: {output.argmax().item()}")
        plt.tight_layout()
        plt.savefig(output_dir / f"example_{i}.png")
        plt.close()
    return