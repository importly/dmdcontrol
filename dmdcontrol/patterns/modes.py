"""Pattern mode registry. Maps --test name -> (label, builder).

Each builder takes the PatternEngine and returns (patterns_or_None, dynamic_kind).
- patterns: passed to engine.pack_patterns(); None for dynamic modes that generate frames directly.
- dynamic_kind: None for static; otherwise selects a dynamic frame provider.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import NamedTuple, Protocol

import numpy as np
from numpy.typing import NDArray

from dmdcontrol.patterns.visual import (
    generate_coarse_grid_rgb,
    generate_coarse_lines_rgb,
)
from dmdcontrol.support.constants import (
    DEFAULT_CALIBRATION_SQUARE_FRACTION,
    DMD_HEIGHT,
    DMD_WIDTH,
    MIN_CALIBRATION_SQUARE_PX,
)

BinaryMask = NDArray[np.uint8]
RGBFrame = NDArray[np.uint8]


class PatternBuildResult(NamedTuple):
    patterns: list[BinaryMask] | None
    dynamic_kind: str | None


class PatternMode(NamedTuple):
    label: str
    builder: "PatternBuilder"


class BuiltPattern(NamedTuple):
    label: str
    patterns: list[BinaryMask] | None
    dynamic_kind: str | None


class PatternBuildEngine(Protocol):
    width: int
    height: int

    def generate_checkerboard(self) -> list[BinaryMask]:
        ...

    def rgb_to_binary_patterns(self, rgb_array: RGBFrame) -> list[BinaryMask]:
        ...


PatternBuilder = Callable[[PatternBuildEngine], PatternBuildResult]

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


@dataclass(frozen=True)
class CalibrationSquareState:
    x: float
    y: float
    size: float
    angle_deg: float = 0.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def default_calibration_square_state(
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> CalibrationSquareState:
    size = max(
        MIN_CALIBRATION_SQUARE_PX,
        min(width,
            height) * DEFAULT_CALIBRATION_SQUARE_FRACTION,
    )
    return CalibrationSquareState(
        x=width / 2.0,
        y=height / 2.0,
        size=float(size),
        angle_deg=0.0,
    )


def clamp_calibration_square_state(
    state: CalibrationSquareState,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> CalibrationSquareState:
    max_size = max(MIN_CALIBRATION_SQUARE_PX, min(width, height))
    return CalibrationSquareState(
        x=float(_clamp(state.x,
                       0.0,
                       max(0.0,
                           width - 1.0))),
        y=float(_clamp(state.y,
                       0.0,
                       max(0.0,
                           height - 1.0))),
        size=float(_clamp(state.size,
                          MIN_CALIBRATION_SQUARE_PX,
                          max_size)),
        angle_deg=float(state.angle_deg % 360.0),
    )


def calibration_square_bounds(
    state: CalibrationSquareState,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> tuple[int, int, int, int]:
    half = state.size / 2.0
    angle = np.deg2rad(state.angle_deg)
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    xs = []
    ys = []
    for local_x, local_y in (
        (-half, -half),
        (half, -half),
        (half, half),
        (-half, half),
    ):
        xs.append(state.x + cos_a * local_x - sin_a * local_y)
        ys.append(state.y + sin_a * local_x + cos_a * local_y)
    return (
        int(_clamp(np.floor(min(xs)),
                   0,
                   max(0,
                       width - 1))),
        int(_clamp(np.floor(min(ys)),
                   0,
                   max(0,
                       height - 1))),
        int(_clamp(np.ceil(max(xs)),
                   0,
                   max(0,
                       width - 1))),
        int(_clamp(np.ceil(max(ys)),
                   0,
                   max(0,
                       height - 1))),
    )


def apply_calibration_square_commands(
    state: CalibrationSquareState,
    commands: Iterable[str],
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    move_px: int = 10,
    rotation_deg: float = 2,
    size_step_px: int = 10,
) -> CalibrationSquareState:
    x = state.x
    y = state.y
    size = state.size
    angle = state.angle_deg
    for command in commands:
        command = command.lower()
        if command == "w":
            y -= move_px
        elif command == "s":
            y += move_px
        elif command == "a":
            x -= move_px
        elif command == "d":
            x += move_px
        elif command == "q":
            angle -= rotation_deg
        elif command == "e":
            angle += rotation_deg
        elif command == "r":
            size += size_step_px
        elif command == "f":
            size -= size_step_px
    return clamp_calibration_square_state(
        CalibrationSquareState(x=x,
                               y=y,
                               size=size,
                               angle_deg=angle),
        width=width,
        height=height,
    )


def generate_calibration_square_mask(
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    center_x: float | None = None,
    center_y: float | None = None,
    size_px: float | None = None,
    angle_deg: float = 0.0,
) -> BinaryMask:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if center_x is None:
        center_x = width / 2.0
    if center_y is None:
        center_y = height / 2.0
    if size_px is None:
        size_px = default_calibration_square_state(width, height).size
    if size_px <= 0:
        raise ValueError("size_px must be positive")

    mask = np.zeros((height, width), dtype=np.uint8)
    half = size_px / 2.0
    radius = int(np.ceil(half * np.sqrt(2.0))) + 2
    x0 = max(0, int(np.floor(center_x - radius)))
    x1 = min(width, int(np.ceil(center_x + radius)) + 1)
    y0 = max(0, int(np.floor(center_y - radius)))
    y1 = min(height, int(np.ceil(center_y + radius)) + 1)
    if x1 <= x0 or y1 <= y0:
        return mask

    yy, xx = np.ogrid[y0:y1, x0:x1]
    dx = xx - center_x
    dy = yy - center_y
    angle = np.deg2rad(angle_deg)
    cos_a = np.cos(angle)
    sin_a = np.sin(angle)
    local_x = cos_a * dx + sin_a * dy
    local_y = -sin_a * dx + cos_a * dy
    local_mask = (np.abs(local_x) <= half) & (np.abs(local_y) <= half)
    mask[y0:y1, x0:x1][local_mask] = 1
    return mask


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
    min_stroke_px: int = 1,
) -> None:
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
    size_px: int | None = None,
) -> RGBFrame:
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


def _grid(engine: PatternBuildEngine) -> PatternBuildResult:
    rgb = generate_coarse_grid_rgb(width=engine.width, height=engine.height)
    return PatternBuildResult(engine.rgb_to_binary_patterns(rgb), None)


def _bands(engine: PatternBuildEngine) -> PatternBuildResult:
    rgb = generate_coarse_lines_rgb(width=engine.width, height=engine.height)
    return PatternBuildResult(engine.rgb_to_binary_patterns(rgb), None)


PATTERN_MODES: dict[str, PatternMode] = {
    #    label                                   pattern generator          dynamic or not
    "checkerboard": PatternMode(
        "Static Checkerboard",
        lambda e: PatternBuildResult(e.generate_checkerboard(), None),
    ),
    "grid": PatternMode("Grid", _grid),
    "bands": PatternMode("Bands", _bands),
    "calibr-square": PatternMode(
        "Interactive Calibration Square",
        lambda e: PatternBuildResult(None, "calibr-square"),
    ),
    "snake": PatternMode("60FPS Snake", lambda e: PatternBuildResult(None, "snake")),
    "clock": PatternMode("Microsecond Clock", lambda e: PatternBuildResult(None, "clock")),
    "kernel": PatternMode(
        "3x3 Kernel Variations (512 patterns)",
        lambda e: PatternBuildResult(None, "kernel"),
    ),
}

PATTERN_NAMES = list(PATTERN_MODES.keys())


def build_patterns(
    engine: PatternBuildEngine,
    mode: str,
) -> BuiltPattern:
    """Returns (label, patterns_or_None, dynamic_kind) for the given mode name."""
    pattern_mode = PATTERN_MODES[mode]
    result = pattern_mode.builder(engine)
    return BuiltPattern(pattern_mode.label, result.patterns, result.dynamic_kind)
