"""Optical convolutions on the rig: the four sign captures of a pass, and their combination.

collect.py stores the raw captures and the combination per sample; bcnn's Conv2dEODLA calls
dmd_conv for the combination alone.
"""

from __future__ import annotations

import logging
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from dmdcontrol.utils import CONFIG

from .display_sequence import build_kernel_sequence

if TYPE_CHECKING:
    from dmdcontrol.camera import CameraProphsee

    from .rig import PairRig

log = logging.getLogger('DmdConv')

TERMS = ('k+ fm+', 'k+ fm-', 'k- fm+', 'k- fm-')  # capture order, and the order of capture_terms' first axis


def capture_terms(rig: PairRig, fm: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """The four captures of N samples: fm (N, h, w), kernel (N, kh, kw) or one (kh, kw), all +-1.

    Returns (4, N, ROI height, ROI width) event counts in TERMS order. A pass that drops frames is
    redone, up to Run.Kernel.max_attempts passes.
    """
    settings = CONFIG.Run.Kernel
    for attempt in range(1, settings.max_attempts + 1):
        capture = rig.play(build_kernel_sequence(fm, kernel))
        if not capture.dropped:
            break
        log.warning('Pass dropped %d frames (attempt %d of %d)', capture.dropped, attempt, settings.max_attempts)
    else:
        raise RuntimeError(f'every one of {settings.max_attempts} passes dropped frames')

    frames = rig.camera.accumulate(capture.semantic[0::2], capture.events)  # content frames only
    return frames.reshape(len(TERMS), len(fm), *frames.shape[1:])


def combine(terms: np.ndarray, gamma: float) -> np.ndarray:
    """(4, ..., H, W) captures in TERMS order -> (k+ fm+) - (k+ fm-) - (k- fm+) + (k- fm-), each raised to gamma.

    All four share one exposure: no per-capture scaling.
    """
    k_pos_fm_pos, k_pos_fm_neg, k_neg_fm_pos, k_neg_fm_neg = (np.asarray(term, dtype=np.float64) ** gamma
                                                              for term in terms)
    return k_pos_fm_pos - k_pos_fm_neg - k_neg_fm_pos + k_neg_fm_neg


def save_sheets(camera: CameraProphsee, terms: np.ndarray, conv: np.ndarray, sheet_path: Path) -> None:
    """<name>_frames.png: every capture, four blocks of N; <name>_conv.png: the combination (mid-grey = 0)."""
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    frames = terms.reshape(-1, *terms.shape[2:])
    camera.contact_sheet(frames, sheet_path.with_name(f'{sheet_path.name}_frames.png'), (20, ceil(len(frames) / 20)))
    camera.contact_sheet(conv, sheet_path.with_name(f'{sheet_path.name}_conv.png'), (20, ceil(len(conv) / 20)),
                         signed=True)


def dmd_conv(rig: PairRig, fm: np.ndarray, kernel: np.ndarray, sheet_path: Path | None = None) -> np.ndarray:
    """Optical convolution of N feature maps fm (N, h, w) with kernel (kh, kw) or (N, kh, kw), all +-1.

    Returns (N, ROI height, ROI width): the four captures combined (see combine). sheet_path, if
    given, gets the contact sheets (see save_sheets).
    """
    terms = capture_terms(rig, fm, kernel)
    conv = combine(terms, CONFIG.Run.Kernel.gamma)
    if sheet_path is not None:
        save_sheets(rig.camera, terms, conv, sheet_path)
    return conv
