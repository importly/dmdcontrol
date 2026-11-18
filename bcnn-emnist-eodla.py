import os
import sys
import argparse
# Args
parser = argparse.ArgumentParser()
parser.add_argument('--gpu', type=int, default=0, help='GPU device ID to use (default: 2)')
parser.add_argument('--config', type=str, default='config.yaml', help='Path to the configuration file (default: config.yaml)')
args = parser.parse_args()

# GPU
os.environ['CUDA_DEVICE_ORDER'] = 'PCI_BUS_ID'
os.environ['CUDA_VISIBLE_DEVICES'] = str(args.gpu)

from pathlib import Path
import argparse
import requests
import yaml
from tqdm import tqdm
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
import matplotlib.pyplot as plt
from bcnn.datasets import ParanoiaDigitsVsLetters as DigitsVsLetters
from bcnn.models import BinaryCNNSingleBin
from bcnn.helpers import test, examples
from bcnn.color import Font

if __name__ == '__main__':  # the camera's process and DataLoader workers re-import this file: run nothing there
    # set seed
    torch.manual_seed(42)
    np.random.seed(42)
    generator = torch.Generator().manual_seed(42)

    # set device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"{Font.GREEN}Using {device}{Font.ENDC}")

    # Error alert hook
    orig_excepthook = sys.excepthook

    def global_error_handler(exc_type, exc_value, exc_traceback):
        requests.post('https://ntfy.sh/eodla', data=f'bcnn-emnist-eodla: Uncaught exception: {exc_type.__name__}: {exc_value}'.encode(encoding='utf-8'))
        orig_excepthook(exc_type, exc_value, exc_traceback)

    sys.excepthook = global_error_handler

    # Config file
    config = yaml.safe_load(open(Path(args.config), 'r'))['BCNN']

    # File paths
    root_folder = Path(f'{config['folder']}')
    os.makedirs(root_folder, exist_ok=True)
    checkpoint = Path(config['checkpoint'])

    # dataset and dataloader
    test_perc = config['test_perc']
    train_full = DigitsVsLetters(train=True, download=config['download'], repeat_channels=True)
    train_full, _, _, _ = random_split(train_full, [0.7, 0.21, 0.03, 0.06], generator=generator)
    # train_full, _, _, _ = random_split(train_full, [0.5, 0.35, 0.05, 0.1], generator=generator)
    train_set, val_set, test_set = random_split(train_full, [0.7, 0.1, 0.2], generator=generator)

    if test_perc < 1.0:
        test_set, _ = random_split(test_set, [test_perc, 1 - test_perc], generator=generator)

    test_loader = DataLoader(
        test_set,
        batch_size=int(config['batch_size']),
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    # Hyperparameters
    channels = int(config['channels'])
    cost_fn = nn.BCEWithLogitsLoss()

    # Train
    history = {
        'test_loss': float('inf'),
        'test_acc': 0.0,
        'train_loss': float('inf'),
        'train_acc': 0.0,
        'val_loss': float('inf'),
        'val_acc': 0.0,
    }

    # Instantiate model
    model = BinaryCNNSingleBin(channels=channels, device=device, eodla=True).to(device)
    model.load_state_dict(torch.load(checkpoint, map_location=device), strict=False)

    # Test
    test_loss, test_acc = test(
        model=model,
        data_loader=test_loader,
        cost_fn=cost_fn,
        device=device,
    )
    history['test_loss'] = test_loss
    history['test_acc'] = test_acc
    tqdm.write(f'{Font.GREEN}Test loss: {test_loss:.6f}, Test accuracy: {test_acc:.6f}{Font.ENDC}, Test percentage: {100*test_perc:.0f}%')

    # Final report

    with open(root_folder / 'report.txt', 'w') as f:
        f.write(f'Test loss: {history['test_loss']:.6f}\n')
        f.write(f'Test accuracy: {history['test_acc']:.6f}\n')
        f.write(f'Test percentage: {100*test_perc:.0f}%\n')
        f.write(f'-'*40 + '\n')
        f.write(f'Checkpoint path: {root_folder / "best_model.pt"}\n')
        f.write(f'-'*40 + '\n')
        f.write(f'Model:\n')
        f.write(f'{model}\n')

    # Set seed
    torch.manual_seed(42)
    np.random.seed(42)
    generator = torch.Generator().manual_seed(42)

    test_loader = DataLoader(
        test_set,
        batch_size=256,
        shuffle=False,
        num_workers=0,
        pin_memory=True,
    )

    # Save test and train examples
    examples(
        folder=root_folder / 'test-examples',
        model=model,
        data_loader=test_loader,
        cost_fn=cost_fn,
        device=device,
    )

    requests.post('https://ntfy.sh/eodla', data='BCNN + EODLA testing done!'.encode(encoding='utf-8'))
