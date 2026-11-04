"""Inputs and kernels for kernel runs.

Inputs come from CIFAR-10 and EMNIST in datasets/ (made 16x16, +1 above the dataset mean),
or are random block patterns. Kernels come from datasets/kernels.npz: unique random 9x9 +-1 kernels
stored as their 81 bits, one block per Run.Kernel.seed, so no two runs share a kernel. Make it once:

    uv run python operands.py [--blocks 20] [--block-size 500000]
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.datasets import CIFAR10, EMNIST

from dmdcontrol.utils import WORKSPACE

SOURCES = {'emnist': 0, 'cifar': 1, 'random': 2}  # label column 1, the translator's codes
DATASETS = WORKSPACE / 'datasets'
KERNEL_BYTES = 11  # 81 bits, packed big-endian: the last byte uses only its top bit


# Kernels

def unpack(packed: np.ndarray) -> np.ndarray:
    """(n, 11) packed kernels -> (n, 9, 9) +-1 float32."""
    bits = np.unpackbits(packed, axis=1, count=81).reshape(-1, 9, 9)
    return bits.astype(np.float32) * 2 - 1


def make_kernels(count: int, seed: int) -> np.ndarray:
    """count unique random kernels, packed."""
    rng = np.random.default_rng(seed)
    packed = np.empty((0, KERNEL_BYTES), np.uint8)
    while len(packed) < count:
        new = rng.integers(0, 256, (count - len(packed), KERNEL_BYTES), dtype=np.uint8)
        new[:, -1] &= 0x80
        packed = np.concatenate([packed, new])
        _, keep = np.unique(packed.view(f'V{KERNEL_BYTES}').ravel(), return_index=True)
        packed = packed[np.sort(keep)]
    return packed


def load_kernels(path: Path, seed: int, count: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, str]:
    """count different kernels from block `seed` of kernels.npz -> (kernels, their rows, sha256 of all kernels)."""
    with np.load(path) as f:
        packed, block = f['packed'], int(f['block_size'])
    sha256 = hashlib.sha256(packed.tobytes()).hexdigest()  # of the kernels, not the zip: the same on every machine
    blocks = len(packed) // block
    if not 0 <= seed < blocks or count > block:
        raise ValueError(f'{path} has {blocks} blocks of {block} kernels (seeds 0 to {blocks - 1}); seed {seed} with '
                         f'{count} samples needs a bigger file: uv run python operands.py --blocks ... --block-size ...')
    rows = seed * block + rng.choice(block, count, replace=False)
    return unpack(packed[rows]), rows, sha256


# Inputs

class _Transpose:
    def __call__(self, img: Image.Image) -> Image.Image:
        return img.transpose(Image.Transpose.TRANSPOSE)  # EMNIST is stored transposed


# The translator's pipelines without augmentation. For more data later, its train augmentation
# (CIFAR RandomCrop(32, padding=4) + RandomHorizontalFlip, EMNIST RandomRotation(10)) goes in here.
CIFAR_PIPELINE = T.Compose([T.Resize((16, 16)), T.ToTensor(),
                            T.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)), T.Grayscale(1)])
EMNIST_PIPELINE = T.Compose([_Transpose(), T.Resize((16, 16)), T.ToTensor(), T.Normalize((0.1307,), (0.3081,))])


def _binarize(images: list[torch.Tensor]) -> np.ndarray:
    x = torch.stack(images)[:, 0].numpy()
    return np.where(x > 0, 1.0, -1.0).astype(np.float32)  # Normalize puts the dataset mean at 0


def _pick(dataset, count: int, pipeline: T.Compose, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if count > len(dataset):
        raise ValueError(f'{count} images asked of a {type(dataset).__name__} set of {len(dataset)}')
    rows = rng.choice(len(dataset), count, replace=False)
    images = _binarize([pipeline(dataset[int(i)][0]) for i in rows])
    targets = np.asarray(dataset.targets)[rows]
    return images, np.asarray(targets, np.int64), rows


def _random(count: int, rng: np.random.Generator) -> np.ndarray:
    """count different +-1 block patterns at scales 2, 4, 8 and 16 (the translator's noise inputs)."""
    def draw(n: int) -> np.ndarray:
        out = np.empty((n, 16, 16), np.float32)
        scale = rng.choice([2, 4, 8, 16], n)
        for s in (2, 4, 8, 16):
            if (m := scale == s).any():
                p = rng.integers(0, 2, (int(m.sum()), s, s)).astype(np.float32) * 2 - 1
                out[m] = np.repeat(np.repeat(p, 16 // s, 1), 16 // s, 2)
        return out

    x = draw(count)
    while True:
        _, keep = np.unique(x.reshape(len(x), -1), axis=0, return_index=True)
        if len(keep) == count:
            return x
        x = np.concatenate([x[np.sort(keep)], draw(count - len(keep))])


def _split(count: int, shares: dict[str, float]) -> dict[str, int]:
    """count rows shared out by source, rounding so they add up."""
    n = {s: int(count * f) for s, f in shares.items()}
    for s in sorted(shares, key=lambda s: count * shares[s] - n[s], reverse=True)[:count - sum(n.values())]:
        n[s] += 1
    return n


def load_inputs(count: int, shares: dict[str, float], train: bool,
                rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """count different inputs from the train (or test) sets -> (inputs, labels [class, source, index]).

    EMNIST is half digits (classes 0-9), half letters (10-35).
    """
    n = _split(count, shares)
    parts: list[tuple[np.ndarray, np.ndarray]] = []

    def add(images: np.ndarray, classes: np.ndarray, source: str, rows: np.ndarray) -> None:
        parts.append((images, np.stack([classes, np.full(len(rows), SOURCES[source]), rows], 1).astype(np.float32)))

    if n.get('cifar'):
        images, classes, rows = _pick(CIFAR10(DATASETS / 'cifar10', train=train), n['cifar'], CIFAR_PIPELINE, rng)
        add(images, classes, 'cifar', rows)
    if n.get('emnist'):
        digits, letters = n['emnist'] // 2, n['emnist'] - n['emnist'] // 2
        images, classes, rows = _pick(EMNIST(DATASETS / 'emnist', 'digits', train=train), digits, EMNIST_PIPELINE, rng)
        add(images, classes, 'emnist', rows)
        images, classes, rows = _pick(EMNIST(DATASETS / 'emnist', 'letters', train=train), letters, EMNIST_PIPELINE, rng)
        add(images, classes + 9, 'emnist', rows)  # letters are 1-26 in torchvision
    if n.get('random'):
        add(_random(n['random'], rng), np.zeros(n['random']), 'random', np.arange(n['random']))

    order = rng.permutation(count)
    return np.concatenate([p[0] for p in parts])[order], np.concatenate([p[1] for p in parts])[order]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--blocks', type=int, default=20, help='one per seed: seeds 0 to blocks - 1')
    parser.add_argument('--block-size', type=int, default=500_000, help='the most samples one run can have')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    out = DATASETS / 'kernels.npz'
    out.parent.mkdir(exist_ok=True)
    packed = make_kernels(args.blocks * args.block_size, args.seed)
    np.savez(out, packed=packed, block_size=args.block_size)
    print(f'{args.blocks} blocks of {args.block_size} unique kernels -> {out}, '
          f'sha256 {hashlib.sha256(packed.tobytes()).hexdigest()}')
