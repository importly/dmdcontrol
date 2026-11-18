import os
from pathlib import Path
from typing import Protocol, runtime_checkable
from tqdm import tqdm
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import  DataLoader
# from translator.models import ResUNet
# from translator.simulator import EODLASimTorch


@runtime_checkable
class SupportsUpdateGradient(Protocol):
    '''
    This helps make type checking happy when using update_gradient() on the BCNN modules.
    '''
    def update_gradient(self) -> None:
        ...


def test(
    model: nn.Module, 
    data_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    cost_fn: nn.Module, 
    device: torch.device | None = None,
    ) -> tuple[float, float]:
    '''
    Test loop.
    ## Inputs
    - model `nn.Module`: the model to test
    - data_loader `DataLoader`: dataloader for test set
    - cost_fn `nn.Module`: loss function
    - device `torch.device`: device to test on
    ## Outputs
    - test_loss `float`: average test loss
    - test_acc `float`: average test accuracy
    '''
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    # Test the model
    model.eval()
    test_loss = 0.0
    correct = 0.0
    length = 0
    with torch.no_grad():
        for inputs, targets in tqdm(data_loader, desc='Testing', leave=False, ncols=150):
            inputs, targets = inputs.to(device), targets[:,0].to(device)
            # one hot encode targets
            targets = F.one_hot(targets, num_classes=2).float()

            out, _ = model(inputs)
            loss = cost_fn(out, targets)
            
            batch_size = inputs.size(0)
            test_loss += loss.item() * batch_size
            correct += (out.argmax(dim=1) == targets.argmax(dim=1)).sum().item()
            length += batch_size
            
        test_loss /= length 
        test_acc = 100 * correct / length

    return test_loss, test_acc


def train(
    model: nn.Module,
    optimizer: torch.optim.Optimizer, 
    cost_fn: nn.Module, 
    train_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    val_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    max_epochs: int = 100, 
    patience: int = 10, 
    min_delta: float = 0.001,
    folder: Path | None = None,
    device: torch.device | None = None, 
    ) -> dict:
    '''
    Train and validation loop.
    ## Inputs
    - model `nn.Module`: the model to train
    - optimizer `torch.optim.Optimizer`: optimizer
    - cost_fn `nn.Module`: loss function
    - train_loader `DataLoader`: dataloader for training set
    - val_loader `DataLoader`: dataloader for validation set
    - max_epochs `int` (optional, default = `100`): maximum number of epochs to train for. Default is 100.
    - patience `int` (optional, default = `10`): number of epochs to wait for improvement in validation loss before stopping. Default is 10.
    - min_delta `float` (optional, default = `0.001`): minimum change in validation loss to qualify as an improvement. Default is 0.001.
    - device `torch.device`: device to train on
    ## Outputs
    - history `dict[str, np.ndarray]`: dict containing training and validation loss and accuracy history
    - best_val_loss `float`: best validation loss achieved during training
    '''
    if device is None:
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    # Initialize history and best state
    history = {
        'train_loss': [],
        'train_acc': [],
        'val_loss': [],
        'val_acc': [],
        }
    best_val_loss = float('inf')
    best_val_acc = 0.0
    best_state = None
    epochs_no_improve = 0
    
    # Train the model
    for epoch in tqdm(range(max_epochs), desc='Epochs', ncols=150):
        model.train()
        # Set translator and optics_sim to eval mode if they exist
        # for module in model.children():
        #     for submodule in module.children():
        #         if isinstance(submodule, ResUNet) or isinstance(submodule, EODLASimTorch):
        #             submodule.eval()
        # for module in model.modules():
            # if isinstance(module, EODLASimTorch):
            #     module.eval()
        avg_loss = 0.0
        avg_acc = 0.0
        length = 0
        for inputs, targets in tqdm(train_loader, desc=f'Training', leave=False, ncols=150):
            inputs, targets = inputs.to(device), targets[:,0].to(device)
            # one hot encode targets
            targets = F.one_hot(targets, num_classes=2).float()
            
            optimizer.zero_grad()
            with torch.autocast(device_type=str(device), dtype=torch.bfloat16):
                out, _ = model(inputs)
                loss = cost_fn(out, targets)
            loss.backward()
            if model.binary_conv_layers:  # Check if there are any binary conv layers
                for layer in model.binary_conv_layers: # pyright: ignore
                    layer.update_gradient()
            optimizer.step()
            
            batch_size = inputs.size(0)
            avg_loss += loss.item() * batch_size
            avg_acc += (out.argmax(dim=1) == targets.argmax(dim=1)).sum().item()
            length += batch_size

        history['train_loss'].append(avg_loss / length)
        history['train_acc'].append((avg_acc / length) * 100)
            
        # validation
        val_loss, val_corr = test(model, val_loader, cost_fn, device)
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_corr)

        # Early stopping check
        if val_loss + min_delta < best_val_loss:
            best_val_loss = val_loss
            best_val_acc = val_corr
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        else:
            epochs_no_improve += 1
            if epochs_no_improve >= patience:
                break
            
        if epoch % 1 == 0:
            tqdm.write(f'Epoch {epoch+1}/{max_epochs} - Train Loss: {history["train_loss"][-1]:.4f}, Train Acc: {history["train_acc"][-1]:.2f}%, Val Loss: {val_loss:.4f}, Val Acc: {val_corr:.2f}%')
            if folder is not None:
                torch.save(model.state_dict(), folder / 'model_checkpoint.pt')

    history.update({
        'best_val_loss': best_val_loss,
        'best_val_acc': best_val_acc,
        'best_state': best_state,
        'epochs_run': epoch + 1,
        'epochs_no_improve': epochs_no_improve,
    }) # pyright: ignore

    return history


def examples(
    folder: Path,
    model: nn.Module, 
    data_loader: DataLoader[tuple[torch.Tensor, torch.FloatTensor]], 
    cost_fn: nn.Module | None = None, 
    device: torch.device | None = None,
    ) -> None:
    '''
    Test loop.
    ## Inputs
    - folder `Path`: path to save examples in.
    - model `nn.Module`: the model to test
    - data_loader `DataLoader`: dataloader for test set
    - cost_fn `nn.Module` (optional): loss function to use for testing. If None, defaults to `nn.HuberLoss()`.
    - device `torch.device`: device to test on
    ## Outputs
    - None (saves test results to the output directory)
    '''
    if device is None:
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    if cost_fn is None:
        cost_fn = nn.HuberLoss()
        
    os.makedirs(folder, exist_ok=True)
    
    model.eval()
    with torch.no_grad():
        for inputs, targets in data_loader:
            inputs, targets = inputs.to(device), targets.to(device)
            out, layers_out = model(inputs)
            break

    # Save batch of examples
    torch.save({
        'inputs': inputs.cpu(),
        'targets': targets.cpu(),
        'out': out.cpu(),
        'layers_out': [layer.cpu() for layer in layers_out],
        }, folder / 'examples.pt')

    # Save images
    layers = [f'Layer {i+1}' for i in range(len(layers_out))]
    for i, (input_img, target, output) in tqdm(enumerate(zip(inputs, targets, out)), total=len(inputs)): 
        fig, axes = plt.subplots(1, len(layers)+1, figsize=(4*(len(layers)+1), 5))
        input_img = input_img.cpu().permute(1, 2, 0)  # CxHxW to HxWxC
        axes[0].imshow((input_img - input_img.min()) / (input_img.max() - input_img.min()), cmap='gray')
        axes[0].set_title(f'Input')
        axes[0].axis('off')
        for j in range(len(layers)):
            img = layers_out[j][i][0].cpu().squeeze(0)
            if img.ndim == 3:  
                img = img.permute(1, 2, 0)  # CxHxW to HxWxC
            axes[j + 1].imshow(img, cmap='gray')
            axes[j + 1].set_title(f'{layers[j]}')
            axes[j + 1].axis('off')
        fig.suptitle(f'Target: {target[0].argmax().item()} - Output: {output.argmax().item()}')
        plt.tight_layout()
        plt.savefig(folder / f'example_{i}.png')
        plt.close()
    return
