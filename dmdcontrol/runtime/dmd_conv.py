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
from PIL import Image, ImageDraw, ImageFont

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

    frames = rig.camera.accumulate(capture.semantic[2::2], capture.events)  # content frames after the warm-up
    return frames.reshape(len(TERMS), len(fm), *frames.shape[1:])


def combine(terms: np.ndarray, gamma: float) -> np.ndarray:
    """(4, ..., H, W) captures in TERMS order -> (k+ fm+) - (k+ fm-) - (k- fm+) + (k- fm-), each raised to gamma.

    All four share one exposure: no per-capture scaling.
    """
    k_pos_fm_pos, k_pos_fm_neg, k_neg_fm_pos, k_neg_fm_neg = (np.asarray(term, dtype=np.float64) ** gamma
                                                              for term in terms)
    return k_pos_fm_pos - k_pos_fm_neg - k_neg_fm_pos + k_neg_fm_neg


def save_sheets(camera: CameraProphsee, terms: np.ndarray, conv: np.ndarray, sheet_path: Path) -> None:
    """<name>_frames.png: every capture, grouped by sample; <name>_conv.png: the combination (mid-grey = 0)."""
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    frames_sheet(terms, sheet_path.with_name(f'{sheet_path.name}_frames.png'))
    camera.contact_sheet(conv, sheet_path.with_name(f'{sheet_path.name}_conv.png'), (20, ceil(len(conv) / 20)),
                         signed=True)


def frames_sheet(terms: np.ndarray, path: Path, per_row: int = 10) -> None:
    """(4, N, H, W) captures -> one labelled 2x2 block per sample: k+ / k- by row, fm+ / fm- by column."""
    n, height, width = terms.shape[1:]
    gap, inner, label_h, top = 24, 4, 32, 56
    group_w, group_h = 2 * width + inner, 2 * height + inner
    big, small = ImageFont.load_default(size=26), ImageFont.load_default(size=17)
    peak = float(np.percentile(terms, 99.9)) or 1.0
    sheet = Image.new('L', (gap + per_row * (group_w + gap), top + ceil(n / per_row) * (label_h + group_h + gap)), 40)
    draw = ImageDraw.Draw(sheet)
    draw.text((gap, 14), f'One block per sample (#index in the pass): top row k+, bottom row k-; left fm+, right fm-. '
              f'ON events, black 0 to white {peak:.0f}, one scale for the whole pass.', fill=255, font=big)
    for i in range(n):
        x0 = gap + (i % per_row) * (group_w + gap)
        y0 = top + (i // per_row) * (label_h + group_h + gap)
        draw.text((x0, y0), f'#{i}', fill=255, font=big)
        for t, name in enumerate(TERMS):
            x, y = x0 + (t % 2) * (width + inner), y0 + label_h + (t // 2) * (height + inner)
            pixels = np.clip(np.asarray(terms[t, i], np.float64) * (255 / peak), 0, 255).astype(np.uint8)
            sheet.paste(Image.fromarray(pixels), (x, y))
            draw.rectangle(draw.textbbox((x + 4, y + 3), name, font=small), fill=0)
            draw.text((x + 4, y + 3), name, fill=255, font=small)
    sheet.save(path)
    log.info('Saved frames sheet to %s', path)


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
