"""Inputs and kernels for kernel runs.

Inputs come from CIFAR-10 and EMNIST in datasets/ (made 16x16, +1 above the dataset mean),
or are random block patterns. Kernels come from datasets/kernels.npz: unique random 9x9 +-1 kernels
stored as their 81 bits, one block per Run.Kernel.seed, so no two runs share a kernel. Make it once:

    uv run python operands.py [--blocks 20] [--block-size 500000]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np
import torch
import torchvision.transforms as T
from PIL import Image
from torchvision.datasets import CIFAR10, EMNIST

from dmdcontrol.utils import WORKSPACE

SOURCES = {'emnist': 0, 'cifar': 1, 'random': 2}  # label column 1, the translator's codes
DATASETS = WORKSPACE / 'datasets'
log = logging.getLogger('operands')
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


def pattern_keys(x: np.ndarray) -> list[bytes]:
    """+-1 images (n, h, w) -> one key each, equal exactly when the images are."""
    return [row.tobytes() for row in np.packbits(x.reshape(len(x), -1) > 0, axis=1)]


@dataclass
class Used:
    """What earlier runs used: their seeds, dataset images (by row) and input patterns, by train or test."""

    seeds: set[int] = field(default_factory=set)
    images: dict[tuple[bool, str], set[int]] = field(default_factory=lambda: defaultdict(set))
    patterns: dict[bool, set[bytes]] = field(default_factory=lambda: {True: set(), False: set()})


def used_operands(root: Path) -> Used:
    """Everything the data.h5 files under root used, apart from seed 0 (tests) and runs from before operands.py."""
    used = Used()
    for path in sorted(root.rglob('data.h5')):
        with h5py.File(path, 'r') as f:
            if 'sources' not in f.attrs or int(f.attrs['seed']) == 0:
                continue
            seed, train, label, x = int(f.attrs['seed']), bool(f.attrs['train']), f['label'][:], f['input16'][:]
        used.seeds.add(seed)
        cls, src, row = label[:, 0], label[:, 1], label[:, 2].astype(np.int64)
        emnist = src == SOURCES['emnist']
        for name, m in (('cifar', src == SOURCES['cifar']), ('digits', emnist & (cls < 10)), ('letters', emnist & (cls >= 10))):
            used.images[(train, name)].update(row[m].tolist())
        used.patterns[train].update(pattern_keys(x))
    return used


def _pick(dataset, name: str, count: int, pipeline: T.Compose, rng: np.random.Generator, exclude: set[int],
          banned: set[bytes]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """count images from rows not in exclude, skipping any whose +-1 pattern is in banned."""
    if count == 0:
        return np.empty((0, 16, 16), np.float32), np.empty(0, np.int64), np.empty(0, np.int64)
    rows = np.setdiff1d(np.arange(len(dataset)), np.fromiter(exclude, np.int64, len(exclude)))
    taken, images, matched = [], [], 0
    for i in rng.permutation(rows):
        image = _binarize([pipeline(dataset[int(i)][0])])[0]
        if banned and pattern_keys(image[None])[0] in banned:
            matched += 1
            continue
        taken.append(i)
        images.append(image)
        if len(taken) == count:
            break
    if len(taken) < count:
        raise ValueError(f'{count} {name} images asked for but only {len(taken)} are left ({len(exclude)} used by earlier '
                         f'runs, {matched} match an input of the other split): ask for fewer, or set '
                         f'Run.Kernel.reuse_images')
    log.info('%d %s images, leaving out %d used by earlier runs and %d matching an input of the other split', count,
             name, len(exclude), matched)
    rows = np.array(taken)
    return np.stack(images), np.asarray(dataset.targets)[rows].astype(np.int64), rows


def _random(count: int, rng: np.random.Generator, banned: set[bytes]) -> np.ndarray:
    """count different +-1 block patterns at scales 2, 4, 8 and 16 (the translator's noise inputs), none in banned."""
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
        keep = np.sort(keep)
        if banned:
            keep = keep[[key not in banned for key in pattern_keys(x[keep])]]
        if len(keep) == count:
            return x[keep]
        x = np.concatenate([x[keep], draw(count - len(keep))])


def _split(count: int, shares: dict[str, float]) -> dict[str, int]:
    """count rows shared out by source, rounding so they add up."""
    n = {s: int(count * f) for s, f in shares.items()}
    for s in sorted(shares, key=lambda s: count * shares[s] - n[s], reverse=True)[:count - sum(n.values())]:
        n[s] += 1
    return n


def load_inputs(count: int, shares: dict[str, float], train: bool, rng: np.random.Generator,
                used: Used | None = None, reuse_images: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """count different inputs from the train (or test) sets -> (inputs, labels [class, source, index]).

    EMNIST is half digits (classes 0-9), half letters (10-35). With used, images earlier runs used are left out
    (unless reuse_images) and so is any input matching one of the other split's, so train and test never share one.
    """
    n = _split(count, shares)
    banned = used.patterns[not train] if used is not None else set()
    parts: list[tuple[np.ndarray, np.ndarray]] = []

    def add(images: np.ndarray, classes: np.ndarray, source: str, rows: np.ndarray) -> None:
        parts.append((images, np.stack([classes, np.full(len(rows), SOURCES[source]), rows], 1).astype(np.float32)))

    def pick(dataset, name: str, k: int, pipeline: T.Compose):
        exclude = used.images[(train, name)] if used is not None and not reuse_images else set()
        return _pick(dataset, name, k, pipeline, rng, exclude, banned)

    if n.get('cifar'):
        images, classes, rows = pick(CIFAR10(DATASETS / 'cifar10', train=train), 'cifar', n['cifar'], CIFAR_PIPELINE)
        add(images, classes, 'cifar', rows)
    if n.get('emnist'):
        digits, letters = n['emnist'] // 2, n['emnist'] - n['emnist'] // 2
        images, classes, rows = pick(EMNIST(DATASETS / 'emnist', 'digits', train=train), 'digits', digits, EMNIST_PIPELINE)
        add(images, classes, 'emnist', rows)
        images, classes, rows = pick(EMNIST(DATASETS / 'emnist', 'letters', train=train), 'letters', letters,
                                     EMNIST_PIPELINE)
        add(images, classes + 9, 'emnist', rows)  # letters are 1-26 in torchvision
    if n.get('random'):
        add(_random(n['random'], rng, banned), np.zeros(n['random']), 'random', np.arange(n['random']))

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
