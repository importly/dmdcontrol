"""How well target16 matches conv16: Pearson r and SSIM.

SSIM is the translator's (eodla_translator_model final.py): each 16x16 image min-max scaled to
[0, 1], then skimage.metrics.structural_similarity with data_range 1 and its default 7x7 window.
"""

from __future__ import annotations

import numpy as np
from skimage.metrics import structural_similarity


def minmax(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return (x - x.min()) / (x.max() - x.min() + 1e-12)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    return float(structural_similarity(minmax(a), minmax(b), data_range=1.0))


def r(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(np.ravel(a), np.ravel(b))[0, 1])
