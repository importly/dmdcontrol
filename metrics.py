"""
SSIM is the translator's (eodla_translator_model final.py): each 16x16 image min-max scaled to
[0, 1], then skimage.metrics.structural_similarity with data_range 1 and its default 7x7 window.
"""

from __future__ import annotations

from typing import cast

import numpy as np
from skimage.metrics import structural_similarity


def minmax(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return (x - x.min()) / (x.max() - x.min() + 1e-12)


def ssim(a: np.ndarray, b: np.ndarray) -> float: # data range at one cause all data is normalized before hand. look at
    return float(cast(np.float64, structural_similarity(minmax(a), minmax(b), data_range=1.0)))


def ssim_noscale(a: np.ndarray, b: np.ndarray) -> float:
    return float(cast(np.float64, structural_similarity(a, b, data_range=1.0)))

def r(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(np.ravel(a), np.ravel(b))[0, 1])
