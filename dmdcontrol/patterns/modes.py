"""Pair-shared calibration and decimal count pattern primitives."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dmdcontrol.utils import CONFIG

DMD_WIDTH = CONFIG.get('DMD', {}).get('width')
DMD_HEIGHT = CONFIG.get('DMD', {}).get('height')

BinaryMask = NDArray[np.uint8]
RGBFrame = NDArray[np.uint8]



_DIGIT_SEGMENTS = {
    1: ("b",
        "c"),
    2: ("a",
        "b",
        "g",
        "e",
        "d"),
    3: ("a",
        "b",
        "g",
        "c",
        "d"),
    4: ("f",
        "g",
        "b",
        "c"),
    5: ("a",
        "f",
        "g",
        "c",
        "d"),
    6: ("a",
        "f",
        "g",
        "e",
        "c",
        "d"),
    7: ("a",
        "b",
        "c"),
    8: ("a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g"),
    9: ("a",
        "b",
        "c",
        "d",
        "f",
        "g"),
}

_DECIMAL_DIGIT_SEGMENTS = {
    0: ("a",
        "b",
        "c",
        "d",
        "e",
        "f"),
    **_DIGIT_SEGMENTS,
}



def _fill_rect(img: RGBFrame, x0: int, y0: int, x1: int, y1: int) -> None:
    height, width = img.shape[:2]
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1, :] = 255


def _draw_digit_segments(
    img: RGBFrame,
    segments: Iterable[str],
    x0: int,
    y0: int,
    digit_w: int,
    digit_h: int,
    min_stroke_px: int = 1,) -> None:
    x1 = x0 + digit_w
    y1 = y0 + digit_h
    mid = (y0 + y1) // 2
    thickness = max(min_stroke_px, int(min(digit_w, digit_h) * 0.16))
    half_t = max(max(1, min_stroke_px // 2), thickness // 2)

    boxes = {
        "a": (x0 + thickness,
              y0,
              x1 - thickness,
              y0 + thickness),
        "b": (x1 - thickness,
              y0 + thickness,
              x1,
              mid),
        "c": (x1 - thickness,
              mid,
              x1,
              y1 - thickness),
        "d": (x0 + thickness,
              y1 - thickness,
              x1 - thickness,
              y1),
        "e": (x0,
              mid,
              x0 + thickness,
              y1 - thickness),
        "f": (x0,
              y0 + thickness,
              x0 + thickness,
              mid),
        "g": (x0 + thickness,
              mid - half_t,
              x1 - thickness,
              mid + half_t),
    }
    for segment in segments:
        _fill_rect(img, *boxes[segment])


def generate_decimal_number_rgb(
    number: int,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    size_px: int | None = None,) -> RGBFrame:
    """Generate a binary RGB seven-segment decimal label frame."""
    if number < 0:
        raise ValueError("number must be non-negative")

    img = np.zeros((height, width, 3), dtype=np.uint8)
    if size_px is not None:
        if size_px <= 0:
            raise ValueError("size_px must be positive")
        digit_h = min(int(size_px), height)
    else:
        digit_h = max(24, int(height * 0.78))

    digits = [int(char) for char in str(int(number))]
    digit_w = max(1, int(digit_h * 0.62))
    gap = max(1, int(digit_w * 0.18)) if len(digits) > 1 else 0
    group_w = len(digits) * digit_w + (len(digits) - 1) * gap
    if group_w > width:
        scale = width / max(1, group_w)
        digit_w = max(1, int(digit_w * scale))
        digit_h = max(1, min(height, int(digit_h * scale)))
        gap = max(1, int(gap * scale)) if len(digits) > 1 else 0
        group_w = len(digits) * digit_w + (len(digits) - 1) * gap

    x = max(0, (width - group_w) // 2)
    y = max(0, (height - digit_h) // 2)
    for digit in digits:
        _draw_digit_segments(
            img,
            _DECIMAL_DIGIT_SEGMENTS[digit],
            x,
            y,
            digit_w,
            digit_h,
        )
        x += digit_w + gap
    return img


