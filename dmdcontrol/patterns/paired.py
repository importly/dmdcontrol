"""Paired 3840x1080 frame composition and OpenGL presentation."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from dmdcontrol.patterns.bitplanes import BitplaneStack, pack_bitplanes_rgb
from dmdcontrol.patterns.modes import generate_decimal_number_rgb
from dmdcontrol.patterns.visual import (
    DEFAULT_COARSE_GRID_SPACING,
    DEFAULT_COARSE_LINE_SPACING,
    generate_coarse_grid_rgb,
    generate_coarse_lines_rgb,
)
from dmdcontrol.support.constants import (
    BITPLANES,
    DEFAULT_ROUTE_MARKER_SIZE,
    DMD_HEIGHT,
    DMD_WIDTH,
    TARGET_HZ,
)
from dmdcontrol.support.logging import logger

PAIR_WIDTH = DMD_WIDTH * 2
PAIR_HEIGHT = DMD_HEIGHT
OFFSET_B = (0, 0)
OFFSET_A = (DMD_WIDTH, 0)

STATIC_PAIR_TESTS = ("checkerboard", "grid", "bands", "dot")
A_COUNT_B_STATIC_PAIR_TEST = "a-count-b-static"
STATIC_IMAGES_PAIR_TEST = "static-images"
DYNAMIC_PAIR_TESTS = ("snake",)
CALIBRATION_DOT_PAIR_TEST = "a-calibr-square-b-dot"
KERNEL_STATIC_PAIR_TEST = "a-kernel-b-static"
RECIPE_PAIR_TESTS = (
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    A_COUNT_B_STATIC_PAIR_TEST,
    STATIC_IMAGES_PAIR_TEST,
)
PAIR_TESTS = STATIC_PAIR_TESTS + DYNAMIC_PAIR_TESTS + RECIPE_PAIR_TESTS
MAX_COUNT_SEQUENCE_FRAMES = 64

RGBFrame = NDArray[np.uint8]
BinaryMask = NDArray[np.uint8]
FrameProvider = Callable[[], RGBFrame]


@dataclass(frozen=True)
class FramePair:
    """Named A/B DMD frames with convenient tuple unpacking."""

    a: RGBFrame
    b: RGBFrame

    def __iter__(self) -> Iterator[RGBFrame]:
        yield self.a
        yield self.b


def as_frame_pair(value: FramePair | tuple[RGBFrame, RGBFrame]) -> FramePair:
    if isinstance(value, FramePair):
        return value
    frame_a, frame_b = value
    return FramePair(frame_a, frame_b)


def _validate_rgb_frame(frame: object, label: str) -> None:
    if not isinstance(frame, np.ndarray):
        raise TypeError(f"{label} must be a numpy array")
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError(f"{label} must have shape HxWx3")
    if frame.dtype != np.uint8:
        raise ValueError(f"{label} must use dtype uint8")


def compose_pair_frame(frame_a: RGBFrame, frame_b: RGBFrame) -> RGBFrame:
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


def _checkerboard(width: int, height: int, block_size: int = 32) -> RGBFrame:
    y, x = np.indices((height, width))
    mask = ((x // block_size + y // block_size) % 2).astype(np.uint8) * 255
    return np.repeat(mask[:, :, None], 3, axis=2)


def load_static_image_frame(
    path: str | PathLike[str],
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    size_px: int = DMD_HEIGHT,
) -> RGBFrame:
    """Load one RGBA/RGB image as a centered RGB frame on a black DMD canvas."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if size_px <= 0:
        raise ValueError("size_px must be positive")

    image_path = Path(path)
    if not image_path.exists():
        raise FileNotFoundError(f"static image not found: {image_path}")

    with Image.open(image_path) as image:
        rgba = image.convert("RGBA")

    source_w, source_h = rgba.size
    if source_w <= 0 or source_h <= 0:
        raise ValueError(f"static image must have non-zero dimensions: {image_path}")

    scale = size_px / max(source_w, source_h)
    target_w = max(1, int(round(source_w * scale)))
    target_h = max(1, int(round(source_h * scale)))
    if target_w > width or target_h > height:
        raise ValueError(
            f"resized static image {image_path} would be {target_w}x{target_h}, "
            f"larger than DMD canvas {width}x{height}")

    resized = rgba.resize((target_w, target_h), resample=Image.Resampling.NEAREST)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    x0 = (width - target_w) // 2
    y0 = (height - target_h) // 2
    canvas.alpha_composite(resized, dest=(x0, y0))
    return np.ascontiguousarray(np.array(canvas.convert("RGB"), dtype=np.uint8))


def _fill_rect_rgb(
    frame: RGBFrame,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    value: int = 255,
) -> None:
    height, width = frame.shape[:2]
    x0 = max(0, min(width, int(x0)))
    x1 = max(0, min(width, int(x1)))
    y0 = max(0, min(height, int(y0)))
    y1 = max(0, min(height, int(y1)))
    if x1 > x0 and y1 > y0:
        frame[y0:y1, x0:x1, :] = value


def _draw_block_letter(frame: RGBFrame, label: str, x0: int, y0: int, cell: int) -> None:
    if label == "A":
        rects = (
            (0,
             1,
             1,
             7),
            (4,
             1,
             5,
             7),
            (1,
             0,
             4,
             1),
            (1,
             3,
             4,
             4),
        )
    else:
        rects = (
            (0,
             0,
             1,
             7),
            (1,
             0,
             4,
             1),
            (1,
             3,
             4,
             4),
            (1,
             6,
             4,
             7),
            (4,
             1,
             5,
             3),
            (4,
             4,
             5,
             6),
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
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    x: float | None = None,
    y: float | None = None,
    radius: int = 40,
    shape: str = "circle",
    invert: bool = False,
) -> RGBFrame:
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
        mask = (xx - x)**2 + (yy - y)**2 <= radius**2
    else:
        mask = (np.abs(xx - x) <= radius) & (np.abs(yy - y) <= radius)

    frame = np.full((height, width, 3), 255 if invert else 0, dtype=np.uint8)
    frame[mask, :] = 0 if invert else 255
    return np.ascontiguousarray(frame)


def _route_mark(frame: RGBFrame, label: str) -> RGBFrame:
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
    mode: str,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    route_label: str = "A",
    dot_x: float | None = None,
    dot_y: float | None = None,
    dot_radius: int = 40,
    dot_shape: str = "circle",
    dot_invert: bool = False,
) -> RGBFrame:
    if mode == "checkerboard":
        frame = _checkerboard(width, height)
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
    elif mode == "grid":
        offset = 0 if route_label == "A" else DEFAULT_COARSE_GRID_SPACING // 2
        frame = generate_coarse_grid_rgb(
            width=width,
            height=height,
            offset_x=offset,
            offset_y=offset,
        )
    elif mode == "bands":
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


def _static_frame(
    mode: str,
    width: int,
    height: int,
    route_label: str,
    dot_radius: int = 40,
) -> RGBFrame:
    return generate_static_frame(
        mode,
        width,
        height,
        route_label,
        dot_radius=dot_radius,
    )


class PairFrameProvider:

    def initial_pair(self) -> FramePair:
        raise NotImplementedError

    def next_pair(self) -> FramePair:
        raise NotImplementedError


class SingleDmdFrameAdapter:
    """Small adapter exposing PatternEngine packing for one half of a paired window."""

    def __init__(self, width: int = DMD_WIDTH, height: int = DMD_HEIGHT, window: object = None):
        self.width = width
        self.height = height
        self.window = window

    def pack_patterns(self, binary_images: Sequence[BinaryMask]) -> RGBFrame:
        return pack_bitplanes_rgb(binary_images, self.width, self.height)


@dataclass
class StaticPairFrameProvider(PairFrameProvider):
    mode_a: str = "checkerboard"
    mode_b: str = "checkerboard"
    width: int = DMD_WIDTH
    height: int = DMD_HEIGHT
    dot_radius: int = 40

    def __post_init__(self) -> None:
        self._frame_a = _static_frame(
            self.mode_a,
            self.width,
            self.height,
            "A",
            dot_radius=self.dot_radius,
        )
        self._frame_b = _static_frame(
            self.mode_b,
            self.width,
            self.height,
            "B",
            dot_radius=self.dot_radius,
        )

    def initial_pair(self) -> FramePair:
        return FramePair(a=self._frame_a, b=self._frame_b)

    def next_pair(self) -> FramePair:
        return FramePair(a=self._frame_a, b=self._frame_b)


@dataclass
class StaticImagePairFrameProvider(PairFrameProvider):
    path_a: str | PathLike[str]
    path_b: str | PathLike[str]
    width: int = DMD_WIDTH
    height: int = DMD_HEIGHT
    size_px: int = DMD_HEIGHT

    def __post_init__(self) -> None:
        self._frame_a = load_static_image_frame(
            self.path_a,
            width=self.width,
            height=self.height,
            size_px=self.size_px,
        )
        self._frame_b = load_static_image_frame(
            self.path_b,
            width=int(self.width),
            height=int(self.height),
            size_px=int(self.size_px),
        )

    def initial_pair(self) -> FramePair:
        return FramePair(a=self._frame_a, b=self._frame_b)

    def next_pair(self) -> FramePair:
        return FramePair(a=self._frame_a, b=self._frame_b)


class DynamicAStaticBPairFrameProvider(PairFrameProvider):

    def __init__(
        self,
        frame_provider_a: FrameProvider,
        frame_b: RGBFrame,
        initial_frame_a: RGBFrame | None = None,
    ) -> None:
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

    def _next_a(self) -> RGBFrame:
        frame_a = self._frame_provider_a()
        _validate_rgb_frame(frame_a, "frame_a")
        if frame_a.shape != self._frame_b.shape:
            raise ValueError(
                f"frame_a and frame_b must have the same shape, got {frame_a.shape} and {self._frame_b.shape}"
            )
        return frame_a

    def initial_pair(self) -> FramePair:
        if self._initial_frame_a is not None:
            return FramePair(a=self._initial_frame_a, b=self._frame_b)
        return FramePair(a=self._next_a(), b=self._frame_b)

    def next_pair(self) -> FramePair:
        return FramePair(a=self._next_a(), b=self._frame_b)


class CalibrationSquareDotPairFrameProvider(DynamicAStaticBPairFrameProvider):

    def __init__(
        self,
        frame_provider_a: FrameProvider,
        frame_b: RGBFrame,
        initial_frame_a: RGBFrame | None = None,
        flicker_a: bool = False,
    ) -> None:
        super().__init__(frame_provider_a, frame_b, initial_frame_a=initial_frame_a)
        self.flicker_a = flicker_a
        self.frame_index = 0
        self._black_frame_a = (
            np.zeros_like(initial_frame_a) if initial_frame_a is not None else None)

    def _remember_black_frame(self, frame_a: RGBFrame) -> None:
        if self._black_frame_a is None:
            self._black_frame_a = np.zeros_like(frame_a)

    def initial_pair(self) -> FramePair:
        frame_pair = as_frame_pair(super().initial_pair())
        self._remember_black_frame(frame_pair.a)
        return frame_pair

    def next_pair(self) -> FramePair:
        self.frame_index += 1
        frame_a = self._next_a()
        self._remember_black_frame(frame_a)
        if self.flicker_a and self.frame_index % 2 == 1:
            assert self._black_frame_a is not None
            return FramePair(a=self._black_frame_a, b=self._frame_b)
        return FramePair(a=frame_a, b=self._frame_b)


class DynamicSnakePairFrameProvider(PairFrameProvider):

    def __init__(
        self,
        width: int = DMD_WIDTH,
        height: int = DMD_HEIGHT,
        cells_x: int = 24,
        cells_y: int = 13,
    ) -> None:
        self.width = width
        self.height = height
        self.cells_x = cells_x
        self.cells_y = cells_y
        self.frame_index = 0

    def _frame_for_index(self, index: int) -> FramePair:
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
                frame[y0:y0 + cell_h, x0:x0 + cell_w, :] = level
        return FramePair(a=_route_mark(frame_a, "A"), b=_route_mark(frame_b, "B"))

    def initial_pair(self) -> FramePair:
        return self._frame_for_index(self.frame_index)

    def next_pair(self) -> FramePair:
        self.frame_index += 1
        return self._frame_for_index(self.frame_index)


def pack_count_sequence_frames(
        count_start: int,
        count_end: int,
        count_slots_per_frame: int,
        width: int,
        height: int,
        size_px: int | None = None,
        count_blank_between_frames: bool = False) -> tuple[RGBFrame, ...]:
    _validate_count_sequence_args(
        count_start,
        count_end,
        count_slots_per_frame,
        count_blank_between_frames=count_blank_between_frames,
    )
    frames: list[RGBFrame] = []
    counts = tuple(range(count_start, count_end + 1))
    for offset in range(0, len(counts), count_slots_per_frame):
        chunk = counts[offset:offset + count_slots_per_frame]
        count_masks = _decimal_number_display_masks(
            chunk,
            width=width,
            height=height,
            size_px=size_px,
        )
        stack = BitplaneStack.from_masks_with_optional_blanks(
            count_masks,
            width=width,
            height=height,
            blank_between_masks=count_blank_between_frames,
        )
        frames.append(stack.to_rgb_frame().array)
    return tuple(frames)


def count_lut_entries_per_frame(
    count_slots_per_frame: int,
    count_blank_between_frames: bool = False,
) -> int:
    return int(count_slots_per_frame) * (2 if count_blank_between_frames else 1)


def _validate_count_sequence_args(
        count_start: int,
        count_end: int,
        count_slots_per_frame: int,
        count_blank_between_frames: bool = False) -> None:
    if count_start <= 0 or count_end <= 0:
        raise ValueError("count range values must be positive")
    if count_start > count_end:
        raise ValueError("count_start must be <= count_end")
    if count_slots_per_frame <= 0 or count_slots_per_frame > BITPLANES:
        raise ValueError(f"count_slots_per_frame must be in the range 1..{BITPLANES}")
    lut_entries = count_lut_entries_per_frame(
        count_slots_per_frame,
        count_blank_between_frames=count_blank_between_frames,
    )

    if lut_entries > BITPLANES:
        raise ValueError(
            f"count_slots_per_frame with blank frames needs {lut_entries} LUT entries, "
            f"but only {BITPLANES} bitplanes are available")
    count_total = count_end - count_start + 1
    if count_total % count_slots_per_frame != 0:
        raise ValueError("count range length must be divisible by count_slots_per_frame")
    frame_count = count_total // count_slots_per_frame
    if frame_count > MAX_COUNT_SEQUENCE_FRAMES:
        raise ValueError(
            f"count sequence can span at most {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames")


def _decimal_number_display_masks(
    numbers: Iterable[int],
    *,
    width: int,
    height: int,
    size_px: int | None = None,
) -> list[BinaryMask]:
    return [
        (
            generate_decimal_number_rgb(
                number,
                width=width,
                height=height,
            size_px=size_px,
            )[:, :, 0] > 0).astype(np.uint8) for number in numbers]


def make_pair_frame_provider(
    test: str,
    test_a: str | None = None,
    test_b: str | None = None,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    static_image_a: str | PathLike[str] | None = None,
    static_image_b: str | PathLike[str] | None = None,
    static_image_size_px: int = DMD_HEIGHT,
    dot_radius: int = 40,
) -> PairFrameProvider:
    if test in STATIC_PAIR_TESTS:
        return StaticPairFrameProvider(
            mode_a=test_a or test,
            mode_b=test_b or test,
            width=width,
            height=height,
            dot_radius=dot_radius,
        )
    if test == STATIC_IMAGES_PAIR_TEST:
        if static_image_a is None or static_image_b is None:
            raise ValueError("static-images requires static_image_a and static_image_b")
        return StaticImagePairFrameProvider(
            static_image_a,
            static_image_b,
            width=width,
            height=height,
            size_px=static_image_size_px,
        )
    if test == "snake":
        return DynamicSnakePairFrameProvider(width=width, height=height)
    raise ValueError(f"Unsupported paired test mode: {test}")


def _load_gl_modules() -> tuple[Any, Any]:
    import glfw
    import OpenGL.GL as gl

    return glfw, gl


class PairedPatternEngine:

    def __init__(
        self,
        width: int = PAIR_WIDTH,
        height: int = PAIR_HEIGHT,
        fps: float = TARGET_HZ,
        x: int = 0,
        y: int = 0,
    ) -> None:
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
            width,
            height,
            "DLPC900 Paired Pattern Engine",
            None,
            None)
        if not self.window:
            self._glfw.terminate()
            raise RuntimeError("Could not create paired GLFW window")

        self._glfw.set_window_pos(self.window, x, y)
        self._glfw.make_context_current(self.window)
        self._glfw.swap_interval(1)

        fb_w, fb_h = self._glfw.get_framebuffer_size(self.window)
        logger.info(
            f"[+] Paired framebuffer: {fb_w}x{fb_h} "
            f"(requested {width}x{height} @ {self.fps}Hz)")
        if fb_w != width or fb_h != height:
            self.cleanup()
            raise RuntimeError(
                f"Paired framebuffer is {fb_w}x{fb_h}, expected {width}x{height}. "
                "Refusing paired run because output halves would not map 1:1 to the DMDs.")

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

    def make_context_current(self) -> None:
        self._glfw.make_context_current(self.window)

    def release_context(self) -> None:
        self._glfw.make_context_current(None)

    def display_pair(self, frame_a: RGBFrame, frame_b: RGBFrame) -> None:
        self.display_frame(compose_pair_frame(frame_a, frame_b))

    def display_frame(self, frame_array: RGBFrame) -> None:
        _validate_rgb_frame(frame_array, "frame_array")
        if frame_array.shape[:2] != (self.height, self.width):
            raise ValueError(
                f"Paired frame shape {frame_array.shape} does not match "
                f"{self.height}x{self.width}x3")

        now = time.perf_counter()
        if self.last_frame_time > 0:
            dt = now - self.last_frame_time
            if dt > self.expected_frame_time * 1.5:
                self.dropped_frames += 1
                if now - self.last_stutter_log > 2.0:
                    logger.warning(
                        f"[WARNING] Paired render stutter: dt={dt * 1000:.2f}ms, "
                        f"dropped_frames={self.dropped_frames}")
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

    def should_close(self) -> bool:
        return self._glfw.window_should_close(self.window) or (
            self._glfw.get_key(self.window,
                               self._glfw.KEY_ESCAPE) == self._glfw.PRESS)

    def cleanup(self) -> None:
        try:
            if getattr(self, "window", None):
                self._glfw.destroy_window(self.window)
        finally:
            self._glfw.terminate()
