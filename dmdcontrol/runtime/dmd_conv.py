"""One optical convolution on the rig: Run.mode kernel calls this once per batch (through bcnn's Conv2dEODLA)."""

from __future__ import annotations

import logging
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from dmdcontrol.utils import CONFIG

from .display_sequence import build_kernel_sequence

if TYPE_CHECKING:
    from .rig import PairRig

log = logging.getLogger('DmdConv')


def dmd_conv(rig: PairRig, fm: np.ndarray, kernel: np.ndarray, sheet_path: Path | None = None) -> np.ndarray:
    """Optical convolution of N feature maps fm (N, h, w) with one kernel (h, w), both +-1.

    One pass gives the four sign products (k+ fm+, k+ fm-, k- fm+, k- fm-); each is min-max
    normalized over the batch and raised to Run.Kernel.gamma, then combined as
    pp - np - pn + nn. Returns (N, ROI height, ROI width). A pass that drops frames is redone.
    sheet_path, if given, gets <name>_frames.png (all four products) and <name>_conv.png.
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
    k_pos_fm_pos, k_pos_fm_neg, k_neg_fm_pos, k_neg_fm_neg = (
        _normalize(part) ** settings.gamma for part in frames.reshape(4, len(fm), *frames.shape[1:]))
    conv = k_pos_fm_pos - k_neg_fm_pos - k_pos_fm_neg + k_neg_fm_neg

    if sheet_path is not None:
        sheet_path.parent.mkdir(parents=True, exist_ok=True)
        rig.camera.contact_sheet(frames, sheet_path.with_name(f'{sheet_path.name}_frames.png'),
                                 (20, ceil(len(frames) / 20)))
        rig.camera.contact_sheet(conv, sheet_path.with_name(f'{sheet_path.name}_conv.png'),
                                 (20, ceil(len(conv) / 20)))
    return conv


def _normalize(part: np.ndarray) -> np.ndarray:
    span = part.max() - part.min()
    return (part - part.min()) / span if span else np.zeros_like(part)
