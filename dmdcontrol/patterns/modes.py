"""Pattern mode registry. Maps --test name -> (label, builder).

Each builder takes the PatternEngine and returns (patterns_or_None, dynamic_kind).
- patterns: passed to engine.pack_patterns(); None for dynamic modes that generate frames directly.
- dynamic_kind: None for static; otherwise selects a dynamic frame provider.
"""

from dataclasses import dataclass

import numpy as np

from dmdcontrol.patterns.numbered_regions import generate_numbered_regions
from dmdcontrol.patterns.visual import generate_coarse_grid_rgb, generate_coarse_lines_rgb
from dmdcontrol.support.constants import (
    DEFAULT_CALIBRATION_SQUARE_FRACTION,
    DEFAULT_NUMBERS_EXPOSURE_US,
    DMD_HEIGHT,
    DMD_WIDTH,
    MIN_CALIBRATION_SQUARE_PX,
    NUMBER_SEQUENCE,
)

_DIGIT_SEGMENTS = {
    1: ("b", "c"),
    2: ("a", "b", "g", "e", "d"),
    3: ("a", "b", "g", "c", "d"),
    4: ("f", "g", "b", "c"),
    5: ("a", "f", "g", "c", "d"),
    6: ("a", "f", "g", "e", "c", "d"),
    7: ("a", "b", "c"),
    8: ("a", "b", "c", "d", "e", "f", "g"),
    9: ("a", "b", "c", "d", "f", "g"),
}

_DECIMAL_DIGIT_SEGMENTS = {
    0: ("a", "b", "c", "d", "e", "f"),
    **_DIGIT_SEGMENTS,
}


@dataclass(frozen=True)
class CalibrationSquareState:
    x: float
    y: float
    size: float
    angle_deg: float = 0.0


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def default_calibration_square_state(width=DMD_WIDTH, height=DMD_HEIGHT):
    size = max(
        MIN_CALIBRATION_SQUARE_PX,
        min(width, height) * DEFAULT_CALIBRATION_SQUARE_FRACTION,
    )
    return CalibrationSquareState(
        x=width / 2.0,
        y=height / 2.0,
        size=float(size),
        angle_deg=0.0,
    )


def clamp_calibration_square_state(state, width=DMD_WIDTH, height=DMD_HEIGHT):
    max_size = max(MIN_CALIBRATION_SQUARE_PX, min(width, height))
    return CalibrationSquareState(
        x=float(_clamp(state.x, 0.0, max(0.0, width - 1.0))),
        y=float(_clamp(state.y, 0.0, max(0.0, height - 1.0))),
        size=float(_clamp(state.size, MIN_CALIBRATION_SQUARE_PX, max_size)),
        angle_deg=float(state.angle_deg % 360.0),
    )


def calibration_square_bounds(state, width=DMD_WIDTH, height=DMD_HEIGHT):
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
        int(_clamp(np.floor(min(xs)), 0, max(0, width - 1))),
        int(_clamp(np.floor(min(ys)), 0, max(0, height - 1))),
        int(_clamp(np.ceil(max(xs)), 0, max(0, width - 1))),
        int(_clamp(np.ceil(max(ys)), 0, max(0, height - 1))),
    )


def apply_calibration_square_commands(
        state,
        commands,
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
        move_px=10,
        rotation_deg=2,
        size_step_px=10,
):
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
        CalibrationSquareState(x=x, y=y, size=size, angle_deg=angle),
        width=width,
        height=height,
    )


def generate_calibration_square_mask(
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
        center_x=None,
        center_y=None,
        size_px=None,
        angle_deg=0.0,
):
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


def _solid_color(color_idx, width=DMD_WIDTH, height=DMD_HEIGHT):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, color_idx] = 255
    return img


def number_index_for_elapsed(elapsed_s, exposure_s, count=len(NUMBER_SEQUENCE)):
    if exposure_s <= 0:
        raise ValueError("exposure_s must be positive")
    if count <= 0:
        raise ValueError("count must be positive")
    elapsed_s = max(0.0, elapsed_s)
    return int(elapsed_s / exposure_s) % count


def _fill_rect(img, x0, y0, x1, y1):
    height, width = img.shape[:2]
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1, :] = 255


def _draw_digit_segments(img, segments, x0, y0, digit_w, digit_h, min_stroke_px=1):
    x1 = x0 + digit_w
    y1 = y0 + digit_h
    mid = (y0 + y1) // 2
    thickness = max(min_stroke_px, int(min(digit_w, digit_h) * 0.16))
    half_t = max(max(1, min_stroke_px // 2), thickness // 2)

    boxes = {
        "a": (x0 + thickness, y0, x1 - thickness, y0 + thickness),
        "b": (x1 - thickness, y0 + thickness, x1, mid),
        "c": (x1 - thickness, mid, x1, y1 - thickness),
        "d": (x0 + thickness, y1 - thickness, x1 - thickness, y1),
        "e": (x0, mid, x0 + thickness, y1 - thickness),
        "f": (x0, y0 + thickness, x0 + thickness, mid),
        "g": (x0 + thickness, mid - half_t, x1 - thickness, mid + half_t),
    }
    for segment in segments:
        _fill_rect(img, *boxes[segment])


def generate_number_rgb(number, width=DMD_WIDTH, height=DMD_HEIGHT, size_px=None):
    """Generate a binary RGB seven-segment digit frame for number mode."""
    if number not in _DIGIT_SEGMENTS:
        raise ValueError("number must be in the range 1..9")

    img = np.zeros((height, width, 3), dtype=np.uint8)
    if size_px is not None:
        if size_px <= 0:
            raise ValueError("size_px must be positive")
        digit_h = min(int(size_px), height)
        digit_w = min(max(16, int(digit_h * 0.62)), width)
    else:
        digit_h = max(24, int(height * 0.78))
        digit_w = min(max(16, int(width * 0.46)), max(16, int(digit_h * 0.62)))
    x0 = (width - digit_w) // 2
    y0 = (height - digit_h) // 2
    _draw_digit_segments(
        img,
        _DIGIT_SEGMENTS[number],
        x0,
        y0,
        digit_w,
        digit_h,
        min_stroke_px=4,
    )
    return img


def generate_decimal_number_rgb(number, width=DMD_WIDTH, height=DMD_HEIGHT, size_px=None):
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


def _numbered(engine):
    rgb = generate_numbered_regions(DMD_WIDTH, DMD_HEIGHT, grid_cols=6, grid_rows=4)
    return engine.rgb_to_binary_patterns(rgb), None


def _coarse_grid(engine):
    rgb = generate_coarse_grid_rgb(width=engine.width, height=engine.height)
    return engine.rgb_to_binary_patterns(rgb), None


def _coarse_lines(engine):
    rgb = generate_coarse_lines_rgb(width=engine.width, height=engine.height)
    return engine.rgb_to_binary_patterns(rgb), None


PATTERN_MODES = {
    #                 label                                   pattern generator          dynamic or not
    "checkerboard": ("Static Checkerboard", lambda e: (e.generate_checkerboard(), None)),
    "ordering": ("Bit Ordering Sweep", lambda e: (e.generate_ordering_diagnostic_patterns(DMD_WIDTH, DMD_HEIGHT), None)),
    "numbered": ("Numbered Regions (6x4 grid)", _numbered),
    "single-pixel": ("1x1 Single Pixel", lambda e: (e.generate_checkerboard(block_size=1), None)),
    "2x2": ("2x2 Checkerboard", lambda e: (e.generate_checkerboard(block_size=2), None)),
    "lines": ("1-pixel Lines", lambda e: (e.generate_lines(), None)),
    "colors": ("Color Channels (R/G/B)", lambda e: (e.rgb_to_binary_patterns(_solid_color(0)), "colors")),
    "coarse-grid": ("Human-Visible Coarse Grid", _coarse_grid),
    "grid": ("Human-Visible Coarse Grid", _coarse_grid),
    "coarse-lines": ("Human-Visible Coarse Lines", _coarse_lines),
    "bands": ("Human-Visible Coarse Lines", _coarse_lines),
    "numbers": ("Sequential Numbers (1-9)", lambda e: (None, "numbers")),
    "calibr-square": ("Interactive Calibration Square", lambda e: (None, "calibr-square")),
    "snake": ("60FPS Snake", lambda e: (None, "snake")),
    "clock": ("Microsecond Clock", lambda e: (None, "clock")),
    "gradient": ("Temporal Gradient", lambda e: (e.generate_gradient(), None)),
    "kernel": ("3x3 Kernel Variations (512 patterns)", lambda e: (None, "kernel")),
}

PATTERN_NAMES = list(PATTERN_MODES.keys())


def build_patterns(engine, mode):
    """Returns (label, patterns_or_None, dynamic_kind) for the given mode name."""
    label, builder = PATTERN_MODES[mode]
    patterns, dynamic_kind = builder(engine)
    return label, patterns, dynamic_kind
