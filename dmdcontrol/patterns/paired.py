"""Paired 3840x1080 frame composition and OpenGL presentation."""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass

import numpy as np

from dmdcontrol.patterns.modes import (
    NUMBER_SEQUENCE,
    generate_decimal_number_rgb,
    generate_number_rgb,
)
from dmdcontrol.patterns.visual import (
    DEFAULT_COARSE_GRID_SPACING,
    DEFAULT_COARSE_LINE_SPACING,
    DEFAULT_ROUTE_MARKER_SIZE,
    generate_coarse_grid_rgb,
    generate_coarse_lines_rgb,
)
from dmdcontrol.support.constants import BITPLANES, DMD_HEIGHT, DMD_WIDTH, TARGET_HZ
from dmdcontrol.support.logging import logger

PAIR_WIDTH = DMD_WIDTH * 2
PAIR_HEIGHT = DMD_HEIGHT
OFFSET_B = (0, 0)
OFFSET_A = (DMD_WIDTH, 0)

HUMAN_VISIBLE_PAIR_TESTS = ("coarse-grid", "grid", "coarse-lines", "bands")
STATIC_PAIR_TESTS = ("checkerboard", "lines", "colors", "dot") + HUMAN_VISIBLE_PAIR_TESTS
NUMBER_PAIR_TEST = "numbers"
A_NUMBERS_B_STATIC_PAIR_TEST = "a-numbers-b-static"
A_COUNT_B_STATIC_PAIR_TEST = "a-count-b-static"
DYNAMIC_PAIR_TESTS = ("gradient", "snake", NUMBER_PAIR_TEST, A_NUMBERS_B_STATIC_PAIR_TEST)
CALIBRATION_DOT_PAIR_TEST = "a-calibr-square-b-dot"
KERNEL_STATIC_PAIR_TEST = "a-kernel-b-static"
RECIPE_PAIR_TESTS = (CALIBRATION_DOT_PAIR_TEST, KERNEL_STATIC_PAIR_TEST, A_COUNT_B_STATIC_PAIR_TEST)
PAIR_TESTS = STATIC_PAIR_TESTS + DYNAMIC_PAIR_TESTS + RECIPE_PAIR_TESTS
MAX_COUNT_SEQUENCE_FRAMES = 64


def _validate_rgb_frame(frame, label):
    if not isinstance(frame, np.ndarray):
        raise TypeError(f"{label} must be a numpy array")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"{label} must have shape HxWx3")
    if frame.dtype != np.uint8:
        raise ValueError(f"{label} must use dtype uint8")


def compose_pair_frame(frame_a, frame_b):
    """Return one RGB frame with B on the left half and A on the right half."""
    _validate_rgb_frame(frame_a, "frame_a")
    _validate_rgb_frame(frame_b, "frame_b")
    if frame_a.shape != frame_b.shape:
        raise ValueError(
            f"frame_a and frame_b must have the same shape, got {frame_a.shape} and {frame_b.shape}"
        )

    height, width, _ = frame_a.shape
    paired = np.empty((height, width * 2, 3), dtype=np.uint8)
    paired[:, :width, :] = frame_b
    paired[:, width:, :] = frame_a
    return paired


def _checkerboard(width, height, block_size=32):
    y, x = np.indices((height, width))
    mask = ((x // block_size + y // block_size) % 2).astype(np.uint8) * 255
    return np.repeat(mask[:, :, None], 3, axis=2)


def _lines(width, height):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, ::2, :] = 255
    img[::16, :, :] = 255
    return img


def _colors(width, height, channel=0):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, channel] = 255
    return img


def _fill_rect_rgb(frame, x0, y0, x1, y1, value=255):
    height, width = frame.shape[:2]
    x0 = max(0, min(width, int(x0)))
    x1 = max(0, min(width, int(x1)))
    y0 = max(0, min(height, int(y0)))
    y1 = max(0, min(height, int(y1)))
    if x1 > x0 and y1 > y0:
        frame[y0:y1, x0:x1, :] = value


def _draw_block_letter(frame, label, x0, y0, cell):
    if label == "A":
        rects = (
            (0, 1, 1, 7),
            (4, 1, 5, 7),
            (1, 0, 4, 1),
            (1, 3, 4, 4),
        )
    else:
        rects = (
            (0, 0, 1, 7),
            (1, 0, 4, 1),
            (1, 3, 4, 4),
            (1, 6, 4, 7),
            (4, 1, 5, 3),
            (4, 4, 5, 6),
        )
    for rx0, ry0, rx1, ry1 in rects:
        _fill_rect_rgb(
            frame,
            x0 + rx0 * cell,
            y0 + ry0 * cell,
            x0 + rx1 * cell,
            y0 + ry1 * cell,
        )


def generate_dot_frame(
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
        x=None,
        y=None,
        radius=40,
        shape="circle",
        invert=False,
):
    """Generate a static RGB dot mask/aperture frame."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if radius <= 0:
        raise ValueError("radius must be positive")
    if shape not in ("circle", "square"):
        raise ValueError("shape must be 'circle' or 'square'")
    if x is None:
        x = width / 2.0
    if y is None:
        y = height / 2.0

    yy, xx = np.ogrid[:height, :width]
    if shape == "circle":
        mask = (xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2
    else:
        mask = (np.abs(xx - x) <= radius) & (np.abs(yy - y) <= radius)

    frame = np.full((height, width, 3), 255 if invert else 0, dtype=np.uint8)
    frame[mask, :] = 0 if invert else 255
    return np.ascontiguousarray(frame)


def _route_mark(frame, label):
    marked = frame.copy()
    height, width = marked.shape[:2]
    if min(width, height) < 32:
        return marked

    max_cell_w = max(1, width // 7)
    max_cell_h = max(1, height // 7)
    cell = max(1, min(DEFAULT_ROUTE_MARKER_SIZE // 7, max_cell_w, max_cell_h))
    letter_w = 5 * cell
    letter_h = 7 * cell
    margin = cell
    x0 = min(margin, max(0, width - margin - letter_w))
    if label == "A":
        y0 = min(margin, max(0, height - margin - letter_h))
    else:
        y0 = max(0, height - margin - letter_h)

    pad = max(1, cell // 2)
    _fill_rect_rgb(marked, x0 - pad, y0 - pad, x0 + letter_w + pad, y0 + letter_h + pad, value=0)
    _draw_block_letter(marked, label, x0, y0, cell)
    return marked


def generate_static_frame(
        mode,
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
        route_label="A",
        dot_x=None,
        dot_y=None,
        dot_radius=40,
        dot_shape="circle",
        dot_invert=False,
):
    if mode == "checkerboard":
        frame = _checkerboard(width, height)
    elif mode == "lines":
        frame = _lines(width, height)
    elif mode == "colors":
        frame = _colors(width, height, channel=0 if route_label == "A" else 1)
    elif mode == "dot":
        return generate_dot_frame(
            width=width,
            height=height,
            x=dot_x,
            y=dot_y,
            radius=dot_radius,
            shape=dot_shape,
            invert=dot_invert,
        )
    elif mode in ("coarse-grid", "grid"):
        offset = 0 if route_label == "A" else DEFAULT_COARSE_GRID_SPACING // 2
        frame = generate_coarse_grid_rgb(
            width=width,
            height=height,
            offset_x=offset,
            offset_y=offset,
        )
    elif mode in ("coarse-lines", "bands"):
        if route_label == "A":
            frame = generate_coarse_lines_rgb(width=width, height=height, orientation="vertical")
        else:
            frame = generate_coarse_lines_rgb(
                width=width,
                height=height,
                orientation="horizontal",
                offset=DEFAULT_COARSE_LINE_SPACING // 2,
            )
    else:
        raise ValueError(f"Unsupported static pair mode: {mode}")
    return _route_mark(frame, route_label)


def _static_frame(mode, width, height, route_label):
    return generate_static_frame(mode, width, height, route_label)


class PairFrameProvider:
    def initial_pair(self):
        raise NotImplementedError

    def next_pair(self):
        raise NotImplementedError


class SingleDmdFrameAdapter:
    """Small adapter exposing PatternEngine packing for one half of a paired window."""

    def __init__(self, width=DMD_WIDTH, height=DMD_HEIGHT, window=None):
        self.width = width
        self.height = height
        self.window = window

    def pack_patterns(self, binary_images):
        r = np.zeros((self.height, self.width), dtype=np.uint8)
        g = np.zeros((self.height, self.width), dtype=np.uint8)
        b = np.zeros((self.height, self.width), dtype=np.uint8)
        for i in range(8):
            g |= binary_images[i] << i
            r |= binary_images[i + 8] << i
            b |= binary_images[i + 16] << i
        return np.ascontiguousarray(np.stack([r, g, b], axis=-1))


@dataclass
class StaticPairFrameProvider(PairFrameProvider):
    mode_a: str = "checkerboard"
    mode_b: str = "checkerboard"
    width: int = DMD_WIDTH
    height: int = DMD_HEIGHT

    def __post_init__(self):
        self._frame_a = _static_frame(self.mode_a, self.width, self.height, "A")
        self._frame_b = _static_frame(self.mode_b, self.width, self.height, "B")

    def initial_pair(self):
        return self._frame_a, self._frame_b

    def next_pair(self):
        return self._frame_a, self._frame_b


class DynamicAStaticBPairFrameProvider(PairFrameProvider):
    def __init__(self, frame_provider_a, frame_b, initial_frame_a=None):
        _validate_rgb_frame(frame_b, "frame_b")
        if initial_frame_a is not None:
            _validate_rgb_frame(initial_frame_a, "initial_frame_a")
            if initial_frame_a.shape != frame_b.shape:
                raise ValueError(
                    f"initial_frame_a and frame_b must have the same shape, got {initial_frame_a.shape} and {frame_b.shape}"
                )
        self._frame_provider_a = frame_provider_a
        self._frame_b = frame_b
        self._initial_frame_a = initial_frame_a

    def _next_a(self):
        frame_a = self._frame_provider_a()
        _validate_rgb_frame(frame_a, "frame_a")
        if frame_a.shape != self._frame_b.shape:
            raise ValueError(
                f"frame_a and frame_b must have the same shape, got {frame_a.shape} and {self._frame_b.shape}"
            )
        return frame_a

    def initial_pair(self):
        if self._initial_frame_a is not None:
            return self._initial_frame_a, self._frame_b
        return self._next_a(), self._frame_b

    def next_pair(self):
        return self._next_a(), self._frame_b


class CalibrationSquareDotPairFrameProvider(DynamicAStaticBPairFrameProvider):
    def __init__(self, frame_provider_a, frame_b, initial_frame_a=None, flicker_a=False):
        super().__init__(frame_provider_a, frame_b, initial_frame_a=initial_frame_a)
        self.flicker_a = flicker_a
        self.frame_index = 0
        self._black_frame_a = (
            np.zeros_like(initial_frame_a) if initial_frame_a is not None else None
        )

    def _remember_black_frame(self, frame_a):
        if self._black_frame_a is None:
            self._black_frame_a = np.zeros_like(frame_a)

    def initial_pair(self):
        frame_a, frame_b = super().initial_pair()
        self._remember_black_frame(frame_a)
        return frame_a, frame_b

    def next_pair(self):
        self.frame_index += 1
        frame_a = self._next_a()
        self._remember_black_frame(frame_a)
        if self.flicker_a and self.frame_index % 2 == 1:
            return self._black_frame_a, self._frame_b
        return frame_a, self._frame_b


class DynamicGradientPairFrameProvider(PairFrameProvider):
    def __init__(self, width=DMD_WIDTH, height=DMD_HEIGHT):
        self.width = width
        self.height = height
        self.frame_index = 0

    def _frame_for_index(self, index):
        x = np.arange(self.width, dtype=np.uint16)[None, :]
        y = np.arange(self.height, dtype=np.uint16)[:, None]
        base = ((x + index * 7) % 256).astype(np.uint8)
        vertical = (((y * 255) // max(1, self.height - 1) + index * 11) % 256).astype(np.uint8)

        frame_a_gray = np.broadcast_to(base, (self.height, self.width))
        frame_b_gray = np.broadcast_to(vertical, (self.height, self.width))
        frame_a = np.repeat(frame_a_gray[:, :, None], 3, axis=2)
        frame_b = np.repeat(frame_b_gray[:, :, None], 3, axis=2)
        return _route_mark(frame_a, "A"), _route_mark(frame_b, "B")

    def initial_pair(self):
        return self._frame_for_index(self.frame_index)

    def next_pair(self):
        self.frame_index += 1
        return self._frame_for_index(self.frame_index)


class DynamicSnakePairFrameProvider(PairFrameProvider):
    def __init__(self, width=DMD_WIDTH, height=DMD_HEIGHT, cells_x=24, cells_y=13):
        self.width = width
        self.height = height
        self.cells_x = cells_x
        self.cells_y = cells_y
        self.frame_index = 0

    def _frame_for_index(self, index):
        frame_a = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame_b = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        cell_w = max(1, self.width // self.cells_x)
        cell_h = max(1, self.height // self.cells_y)
        path_len = self.cells_x * self.cells_y
        head = index % path_len
        for route, frame in (("A", frame_a), ("B", frame_b)):
            offset = 0 if route == "A" else self.cells_x // 2
            for segment in range(6):
                pos = (head - segment + offset) % path_len
                row = pos // self.cells_x
                col = pos % self.cells_x
                x0 = col * cell_w
                y0 = row * cell_h
                level = max(64, 255 - segment * 32)
                frame[y0: y0 + cell_h, x0: x0 + cell_w, :] = level
        return _route_mark(frame_a, "A"), _route_mark(frame_b, "B")

    def initial_pair(self):
        return self._frame_for_index(self.frame_index)

    def next_pair(self):
        self.frame_index += 1
        return self._frame_for_index(self.frame_index)


class NumberSequencePairFrameProvider(PairFrameProvider):
    def __init__(
            self,
            numbers=NUMBER_SEQUENCE,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            size_px=None,
    ):
        if not numbers:
            raise ValueError("numbers must not be empty")
        if len(numbers) > BITPLANES:
            raise ValueError(f"numbers can contain at most {BITPLANES} entries")
        self.numbers = tuple(numbers)
        self.width = width
        self.height = height
        self.size_px = size_px
        self.frame_index = 0
        self._frame = _pack_number_sequence_bitplanes(
            self.numbers,
            width=width,
            height=height,
            size_px=size_px,
        )

    def initial_pair(self):
        return self._frame, self._frame

    def next_pair(self):
        return self._frame, self._frame


class NumberSequenceAStaticBPairFrameProvider(PairFrameProvider):
    def __init__(
            self,
            mode_b="dot",
            numbers=NUMBER_SEQUENCE,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            size_px=None,
            b_dot_x=None,
            b_dot_y=None,
            b_dot_radius=40,
            b_dot_shape="circle",
            b_dot_invert=False,
    ):
        if not numbers:
            raise ValueError("numbers must not be empty")
        if len(numbers) > BITPLANES:
            raise ValueError(f"numbers can contain at most {BITPLANES} entries")
        self.width = width
        self.height = height
        self._frame_a = _pack_number_sequence_bitplanes(
            numbers,
            width=width,
            height=height,
            size_px=size_px,
        )
        self._frame_b = generate_static_frame(
            mode_b,
            width=width,
            height=height,
            route_label="B",
            dot_x=b_dot_x,
            dot_y=b_dot_y,
            dot_radius=b_dot_radius,
            dot_shape=b_dot_shape,
            dot_invert=b_dot_invert,
        )

    def initial_pair(self):
        return self._frame_a, self._frame_b

    def next_pair(self):
        return self._frame_a, self._frame_b


class CountSequenceAStaticBPairFrameProvider(PairFrameProvider):
    def __init__(
            self,
            mode_b="dot",
            count_start=1,
            count_end=100,
            count_slots_per_frame=2,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            size_px=None,
            b_dot_x=None,
            b_dot_y=None,
            b_dot_radius=40,
            b_dot_shape="circle",
            b_dot_invert=False,
    ):
        _validate_count_sequence_args(count_start, count_end, count_slots_per_frame)
        self.width = width
        self.height = height
        self.frame_index = 0
        self._frames_a = _pack_count_sequence_frames(
            count_start,
            count_end,
            count_slots_per_frame,
            width=width,
            height=height,
            size_px=size_px,
        )
        self._frame_b = generate_static_frame(
            mode_b,
            width=width,
            height=height,
            route_label="B",
            dot_x=b_dot_x,
            dot_y=b_dot_y,
            dot_radius=b_dot_radius,
            dot_shape=b_dot_shape,
            dot_invert=b_dot_invert,
        )

    def initial_pair(self):
        return self._frames_a[self.frame_index], self._frame_b

    def next_pair(self):
        self.frame_index = (self.frame_index + 1) % len(self._frames_a)
        return self._frames_a[self.frame_index], self._frame_b


def _pack_number_sequence_bitplanes(numbers, width, height, size_px=None):
    masks = _number_bitplane_masks(numbers, width=width, height=height, size_px=size_px)
    return _pack_binary_masks_bitplanes(masks, width, height)


def _pack_count_sequence_frames(count_start, count_end, count_slots_per_frame, width, height, size_px=None):
    _validate_count_sequence_args(count_start, count_end, count_slots_per_frame)
    frames = []
    counts = _count_sequence_values(count_start, count_end)
    for offset in range(0, len(counts), count_slots_per_frame):
        chunk = counts[offset: offset + count_slots_per_frame]
        masks = _decimal_number_bitplane_masks(chunk, width=width, height=height, size_px=size_px)
        frames.append(_pack_binary_masks_bitplanes(masks, width, height))
    return tuple(frames)


def _validate_count_sequence_args(count_start, count_end, count_slots_per_frame):
    if count_start <= 0 or count_end <= 0:
        raise ValueError("count range values must be positive")
    if count_start > count_end:
        raise ValueError("count_start must be <= count_end")
    if count_slots_per_frame <= 0 or count_slots_per_frame > BITPLANES:
        raise ValueError(f"count_slots_per_frame must be in the range 1..{BITPLANES}")
    count_total = count_end - count_start + 1
    if count_total % count_slots_per_frame != 0:
        raise ValueError("count range length must be divisible by count_slots_per_frame")
    frame_count = count_total // count_slots_per_frame
    if frame_count > MAX_COUNT_SEQUENCE_FRAMES:
        raise ValueError(
            f"count sequence can span at most {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames"
        )


def count_sequence_frame_count(count_start, count_end, count_slots_per_frame):
    _validate_count_sequence_args(count_start, count_end, count_slots_per_frame)
    return (count_end - count_start + 1) // count_slots_per_frame


def _count_sequence_values(count_start, count_end):
    return tuple(range(count_start, count_end + 1))


def _number_bitplane_masks(numbers, *, width, height, size_px=None):
    return [
        (
            generate_number_rgb(
                number,
                width=width,
                height=height,
                size_px=size_px,
            )[:, :, 0] > 0
        ).astype(np.uint8)
        for number in numbers
    ]


def _decimal_number_bitplane_masks(numbers, *, width, height, size_px=None):
    return [
        (
            generate_decimal_number_rgb(
                number,
                width=width,
                height=height,
                size_px=size_px,
            )[:, :, 0] > 0
        ).astype(np.uint8)
        for number in numbers
    ]


def _pack_binary_masks_bitplanes(masks, width, height):
    masks = list(masks)
    if len(masks) > BITPLANES:
        raise ValueError(f"masks can contain at most {BITPLANES} entries")
    masks.extend(
        np.zeros((height, width), dtype=np.uint8)
        for _ in range(BITPLANES - len(masks))
    )

    r = np.zeros((height, width), dtype=np.uint8)
    g = np.zeros((height, width), dtype=np.uint8)
    b = np.zeros((height, width), dtype=np.uint8)
    for bit in range(8):
        g |= masks[bit] << bit
        r |= masks[bit + 8] << bit
        b |= masks[bit + 16] << bit
    return np.ascontiguousarray(np.stack([r, g, b], axis=-1))


def make_pair_frame_provider(
        test,
        test_a=None,
        test_b=None,
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
        numbers=None,
        numbers_size_px=None,
        numbers_exposure_us=None,
        count_start=1,
        count_end=100,
        count_slots_per_frame=2,
        b_dot_x=None,
        b_dot_y=None,
        b_dot_radius=40,
        b_dot_shape="circle",
        b_dot_invert=False,
):
    if test in STATIC_PAIR_TESTS:
        return StaticPairFrameProvider(
            mode_a=test_a or test,
            mode_b=test_b or test,
            width=width,
            height=height,
        )
    if test == "gradient":
        return DynamicGradientPairFrameProvider(width=width, height=height)
    if test == "snake":
        return DynamicSnakePairFrameProvider(width=width, height=height)
    if test == NUMBER_PAIR_TEST:
        return NumberSequencePairFrameProvider(
            numbers=numbers or NUMBER_SEQUENCE,
            width=width,
            height=height,
            size_px=numbers_size_px,
        )
    if test == A_NUMBERS_B_STATIC_PAIR_TEST:
        return NumberSequenceAStaticBPairFrameProvider(
            mode_b=test_b or "dot",
            numbers=numbers or NUMBER_SEQUENCE,
            width=width,
            height=height,
            size_px=numbers_size_px,
            b_dot_x=b_dot_x,
            b_dot_y=b_dot_y,
            b_dot_radius=b_dot_radius,
            b_dot_shape=b_dot_shape,
            b_dot_invert=b_dot_invert,
        )
    if test == A_COUNT_B_STATIC_PAIR_TEST:
        return CountSequenceAStaticBPairFrameProvider(
            mode_b=test_b or "dot",
            count_start=count_start,
            count_end=count_end,
            count_slots_per_frame=count_slots_per_frame,
            width=width,
            height=height,
            size_px=numbers_size_px,
            b_dot_x=b_dot_x,
            b_dot_y=b_dot_y,
            b_dot_radius=b_dot_radius,
            b_dot_shape=b_dot_shape,
            b_dot_invert=b_dot_invert,
        )
    raise ValueError(f"Unsupported paired test mode: {test}")


def _load_gl_modules():
    glfw = importlib.import_module("glfw")
    gl = importlib.import_module("OpenGL.GL")
    return glfw, gl


class PairedPatternEngine:
    def __init__(self, width=PAIR_WIDTH, height=PAIR_HEIGHT, fps=TARGET_HZ, x=0, y=0):
        self.width = width
        self.height = height
        self.fps = fps
        self._glfw, self._gl = _load_gl_modules()

        self.last_frame_time = 0.0
        self.expected_frame_time = 1.0 / fps
        self.dropped_frames = 0
        self.last_stutter_log = 0.0

        if not self._glfw.init():
            raise RuntimeError("Could not initialize GLFW")

        self._glfw.window_hint(self._glfw.DECORATED, self._glfw.FALSE)
        self._glfw.window_hint(self._glfw.RESIZABLE, self._glfw.FALSE)
        self._glfw.window_hint(self._glfw.AUTO_ICONIFY, self._glfw.FALSE)
        self._glfw.window_hint(self._glfw.REFRESH_RATE, self.fps)

        self.window = self._glfw.create_window(
            width, height, "DLPC900 Paired Pattern Engine", None, None
        )
        if not self.window:
            self._glfw.terminate()
            raise RuntimeError("Could not create paired GLFW window")

        self._glfw.set_window_pos(self.window, x, y)
        self._glfw.make_context_current(self.window)
        self._glfw.swap_interval(1)

        fb_w, fb_h = self._glfw.get_framebuffer_size(self.window)
        logger.info(
            f"[+] Paired framebuffer: {fb_w}x{fb_h} "
            f"(requested {width}x{height} @ {self.fps}Hz)"
        )
        if fb_w != width or fb_h != height:
            self.cleanup()
            raise RuntimeError(
                f"Paired framebuffer is {fb_w}x{fb_h}, expected {width}x{height}. "
                "Refusing paired run because output halves would not map 1:1 to the DMDs."
            )

        gl = self._gl
        gl.glViewport(0, 0, fb_w, fb_h)
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        gl.glOrtho(0, width, height, 0, -1, 1)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadIdentity()
        gl.glEnable(gl.GL_TEXTURE_2D)
        self.tex_id = gl.glGenTextures(1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex_id)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)

    def make_context_current(self):
        self._glfw.make_context_current(self.window)

    def release_context(self):
        self._glfw.make_context_current(None)

    def display_pair(self, frame_a, frame_b):
        self.display_frame(compose_pair_frame(frame_a, frame_b))

    def display_frame(self, frame_array):
        _validate_rgb_frame(frame_array, "frame_array")
        if frame_array.shape[:2] != (self.height, self.width):
            raise ValueError(
                f"Paired frame shape {frame_array.shape} does not match "
                f"{self.height}x{self.width}x3"
            )

        now = time.perf_counter()
        if self.last_frame_time > 0:
            dt = now - self.last_frame_time
            if dt > self.expected_frame_time * 1.5:
                self.dropped_frames += 1
                if now - self.last_stutter_log > 2.0:
                    logger.warning(
                        f"[WARNING] Paired render stutter: dt={dt * 1000:.2f}ms, "
                        f"dropped_frames={self.dropped_frames}"
                    )
                    self.last_stutter_log = now
        self.last_frame_time = now

        frame = np.ascontiguousarray(frame_array)
        gl = self._gl
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex_id)
        gl.glTexImage2D(
            gl.GL_TEXTURE_2D,
            0,
            gl.GL_RGB,
            self.width,
            self.height,
            0,
            gl.GL_RGB,
            gl.GL_UNSIGNED_BYTE,
            frame,
        )
        gl.glBegin(gl.GL_QUADS)
        gl.glTexCoord2f(0, 0)
        gl.glVertex2f(0, 0)
        gl.glTexCoord2f(1, 0)
        gl.glVertex2f(self.width, 0)
        gl.glTexCoord2f(1, 1)
        gl.glVertex2f(self.width, self.height)
        gl.glTexCoord2f(0, 1)
        gl.glVertex2f(0, self.height)
        gl.glEnd()
        self._glfw.swap_buffers(self.window)
        self._glfw.poll_events()

    def should_close(self):
        return self._glfw.window_should_close(self.window) or (
                self._glfw.get_key(self.window, self._glfw.KEY_ESCAPE) == self._glfw.PRESS
        )

    def cleanup(self):
        try:
            if getattr(self, "window", None):
                self._glfw.destroy_window(self.window)
        finally:
            self._glfw.terminate()
