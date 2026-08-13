"""Paired 3840x1080 frame composition and OpenGL presentation."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

import glfw
import OpenGL.GL as gl

from dmdcontrol.patterns.bitplanes import BitplaneStack, pack_bitplanes_rgb
from dmdcontrol.patterns.modes import generate_decimal_number_rgb
from dmdcontrol.utils import CONFIG

logger = logging.getLogger('Paired')

BITPLANES = CONFIG.get('DMD', {}).get('bitplanes')
DMD_WIDTH = CONFIG.get('DMD', {}).get('width')
DMD_HEIGHT = CONFIG.get('DMD', {}).get('height')
TARGET_HZ = CONFIG.get('DMD', {}).get('target_hz')

PAIR_WIDTH = DMD_WIDTH * 2
PAIR_HEIGHT = DMD_HEIGHT
OFFSET_B = (0, 0)
OFFSET_A = (DMD_WIDTH, 0)

STATIC_PAIR_TESTS = ("checkerboard", "dot")
A_COUNT_B_STATIC_PAIR_TEST = "a-count-b-static"
STATIC_IMAGES_PAIR_TEST = "static-images"
KERNEL_STATIC_PAIR_TEST = "a-kernel-b-static"
RECIPE_PAIR_TESTS = (
    KERNEL_STATIC_PAIR_TEST,
    A_COUNT_B_STATIC_PAIR_TEST,
    STATIC_IMAGES_PAIR_TEST,
)
PAIR_TESTS = STATIC_PAIR_TESTS + RECIPE_PAIR_TESTS
MAX_COUNT_SEQUENCE_FRAMES = 128

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


def _validate_rgb_frame(frame: object, label: str):
    """
    Checks if frame is in the correct RGB format

    Args:
        frame (object): The frame to validate
        label (str): The label for the frame

    Raises:
        TypeError: Raises if frame is not a numpy array
        ValueError: Raises if frame is not in the correct RGB format
        ValueError: Raises if frame is not uint8
    """
    logger.debug('%s shape: %s, dtype: %s', label, getattr(frame, 'shape', None), getattr(frame, 'dtype', None))
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
    size_px: int = DMD_HEIGHT,) -> RGBFrame:
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
    value: int = 255,) -> None:
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
    invert: bool = False,) -> RGBFrame:
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


def generate_static_frame(
    mode: str,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    route_label: str = "A",
    dot_x: float | None = None,
    dot_y: float | None = None,
    dot_radius: int = 40,
    dot_shape: str = "circle",
    dot_invert: bool = False,) -> RGBFrame:
    if mode == "checkerboard":
        return _checkerboard(width, height)
    if mode == "dot":
        return generate_dot_frame(
            width=width,
            height=height,
            x=dot_x,
            y=dot_y,
            radius=dot_radius,
            shape=dot_shape,
            invert=dot_invert,
        )
    raise ValueError(f"Unsupported static pair mode: {mode}")


def _static_frame(
    mode: str,
    width: int,
    height: int,
    route_label: str,
    dot_radius: int = 40,) -> RGBFrame:
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


class HalfFramePackingAdapter:
    """Pack bitplanes for one half of a paired display sequence."""

    def __init__(self, width: int = DMD_WIDTH, height: int = DMD_HEIGHT, window: object = None):
        self.width = width
        self.height = height
        self.window = window

    def pack_patterns(self, binary_images: Sequence[BinaryMask]) -> RGBFrame:
        return pack_bitplanes_rgb(binary_images, self.width, self.height)


class DynamicAStaticBPairFrameProvider(PairFrameProvider):

    def __init__(
        self,
        frame_provider_a: FrameProvider,
        frame_b: RGBFrame,
        initial_frame_a: RGBFrame | None = None,) -> None:
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
    )
    frames: list[RGBFrame] = []
    counts = tuple(range(count_start, count_end + 1))
    blank_frame = np.zeros((height, width, 3), dtype=np.uint8)
    for count in counts:
        count_mask = _decimal_number_display_masks(
            (count,),
            width=width,
            height=height,
            size_px=size_px,
        )
        stack = BitplaneStack.from_masks(count_mask, width=width, height=height)
        frames.append(stack.to_rgb_frame().array)
        frames.append(blank_frame.copy())
    return tuple(frames)

def pos_img(a: np.ndarray) -> np.ndarray:
    '''
    Makes the positive image of the kernel (pos nums => 255, neg nums => 0)
    '''
    if np.max(a)==0:
        return a
    new_matrix = np.zeros_like(a)
    try:
        new_matrix = a / abs(np.max(a))
    except FloatingPointError:
        pass
    new_matrix += 1
    new_matrix /= 2
    new_matrix *= 255
    return new_matrix.astype(np.uint8)


def neg_img(a: np.ndarray) -> np.ndarray:
    '''
    Makes the negative image of the kernel (pos nums => 0, neg nums => 255)
    '''
    if np.max(a)==0:
        return np.zeros_like(a)+1
    new_matrix = np.zeros_like(a)
    try:
        new_matrix = a / abs(np.max(a))
    except FloatingPointError:
        pass
    new_matrix *= -1
    new_matrix += 1
    new_matrix /= 2
    tmp = new_matrix * 255
    return tmp.astype(np.uint8)


def pack_sequence_frames(data: np.ndarray) -> np.ndarray:
    '''
    Packs a sequence of binary masks into RGB frames. Each mask is split into its positive and negative halfs.
    
    Args:
        data (np.ndarray): A 3D numpy array of shape (batch_size, height, width) containing binary masks.
    '''
    frames = np.zeros((data.shape[0] * 4, data.shape[1], data.shape[2], 3), dtype=np.uint8)
    for i, fm in enumerate(data):
        # Positive 
        pos_mask = pos_img(fm)
        frames[4*i, :, :, 1] = pos_mask
        
        # Negative
        neg_mask = neg_img(fm)
        frames[4*i + 2, :, :, 1] = neg_mask
        
    frames = np.ascontiguousarray(frames)
    return frames

def pack_static_frames(data: np.ndarray, batch_size: int, pos: bool) -> np.ndarray:
    '''
    Packs a sequence of binary masks into RGB frames. Each mask is split into either its positive and negative half.
    
    Args:
        data (np.ndarray): A 3D numpy array of shape (height, width) containing binary masks.
        batch_size (int): The number of frames to pack.
        pos (bool): If True, pack the positive half of the masks; if False, pack the negative half.
    '''
    if len(data.shape) != 2:
        raise ValueError("`data` must be a 2D numpy array")

    frames = pos_img(data) if pos else neg_img(data)
    frames = np.expand_dims(frames, axis=(0,-1))
    frames = np.tile(frames, (batch_size, 1, 1, 3))
    frames = np.ascontiguousarray(frames)
    return frames


def count_lut_entries_per_frame(
    count_slots_per_frame: int,
    count_blank_between_frames: bool = False,) -> int:
    if count_blank_between_frames:
        return 1
    return int(count_slots_per_frame)


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
    if count_blank_between_frames and count_slots_per_frame != 1:
        raise ValueError("count blank insertion requires count_slots_per_frame=1")
    lut_entries = count_lut_entries_per_frame(
        count_slots_per_frame,
        count_blank_between_frames=count_blank_between_frames,
    )

    if lut_entries > BITPLANES:
        raise ValueError(
            f"count_slots_per_frame with blank frames needs {lut_entries} LUT entries, "
            f"but only {BITPLANES} bitplanes are available")
    count_total = count_end - count_start + 1
    if not count_blank_between_frames and count_total % count_slots_per_frame != 0:
        raise ValueError("count range length must be divisible by count_slots_per_frame")
    frame_count = count_total * 2 if count_blank_between_frames else count_total // count_slots_per_frame
    if frame_count > MAX_COUNT_SEQUENCE_FRAMES:
        raise ValueError(
            f"count sequence can span at most {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames")


def _decimal_number_display_masks(
    numbers: Iterable[int],
    *,
    width: int,
    height: int,
    size_px: int | None = None,) -> list[BinaryMask]:
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
    dot_radius: int = 40,) -> PairFrameProvider:
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
    raise ValueError(f"Unsupported paired test mode: {test}")


class PairedPatternEngine:
    """
    A class for managing paired pattern generation and display.
    """
    
    def __init__(self):
        """
        Initializes the paired pattern engine.

        Raises:
            ValueError: Raised if width is leq zero or odd.
            ValueError: Raises if height is leq zero.
            RuntimeError: Raised if GLFW initialization fails.
            RuntimeError: Raised if window creation fails.
            RuntimeError: Raised if context setup fails.
        """
        # Set width
        self.half_width = int(CONFIG.get('DMD', {}).get('width', 1920))
        self.width = self.half_width * 2
        if self.width <= 0 or self.width % 2:
            raise ValueError('Paired width must be a positive even number')
        
        # Set height
        self.height = int(CONFIG.get('DMD', {}).get('height', 1080))
        if self.height <= 0:
            raise ValueError('Paired height must be a positive number')
        
        # Set fps
        self.fps = int(CONFIG.get('DMD', {}).get('target_hz', 60))

        # Frame timing
        self.last_frame_time = 0.0
        self.expected_frame_time = 1.0 / self.fps
        self.dropped_frames = 0
        self.last_stutter_log = 0.0

        # Initialize GLFW and create a window
        if not glfw.init():
            logger.error('Could not initialize GLFW')
            raise RuntimeError('Could not initialize GLFW')

        glfw.window_hint(glfw.DECORATED, glfw.FALSE)
        glfw.window_hint(glfw.RESIZABLE, glfw.FALSE)
        glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
        glfw.window_hint(glfw.REFRESH_RATE, self.fps)

        self.window = glfw.create_window(
            self.width,
            self.height,
            'DLPC900 Paired Pattern Engine',
            None,
            None)
        if not self.window:
            glfw.terminate()
            logger.error('Could not create paired GLFW window')
            raise RuntimeError('Could not create paired GLFW window')

        glfw.set_window_pos(self.window, 0, 0)
        glfw.make_context_current(self.window)
        glfw.swap_interval(1)

        fb_w, fb_h = glfw.get_framebuffer_size(self.window)
        logger.info('Paired framebuffer: %dx%d. Requested %dx%d @ %dHz)', fb_w, fb_h, self.width, self.height, self.fps)
        if fb_w != self.width or fb_h != self.height:
            self.cleanup()
            raise RuntimeError(f'Paired framebuffer is {fb_w}x{fb_h}, expected {self.width}x{self.height}.')

        gl.glViewport(0, 0, fb_w, fb_h)
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        gl.glOrtho(0, self.width, self.height, 0, -1, 1)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadIdentity()
        gl.glEnable(gl.GL_TEXTURE_2D)
        texture_ids = tuple(int(texture_id) for texture_id in gl.glGenTextures(2))
        if len(texture_ids) != 2:
            self.cleanup()
            logger.error('OpenGL allocated %d paired textures, expected 2', len(texture_ids))
            raise RuntimeError(f'OpenGL allocated {len(texture_ids)} paired textures, expected 2')
        self.texture_b, self.texture_a = texture_ids
        self._textures_deleted = False
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        for texture_id in texture_ids:
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
            gl.glTexImage2D(
                gl.GL_TEXTURE_2D,
                0,
                gl.GL_RGB8,
                self.half_width,
                self.height,
                0,
                gl.GL_RGB,
                gl.GL_UNSIGNED_BYTE,
                None,
            )

    def make_context_current(self):
        """
        Makes the context of window current for the calling thread.
        """
        glfw.make_context_current(self.window)

    def release_context(self):
        """
        Releases the context of the window from the calling thread.
        """
        glfw.make_context_current(None)

    def display_pair(self, frame_a: RGBFrame, frame_b: RGBFrame) -> None:
        frame_start = time.perf_counter()
        cadence_dt = (
            frame_start - self.last_frame_time
            if self.last_frame_time > 0.0
            else None
        )
        self.last_frame_time = frame_start

        prepared_a = self._prepare_dmd_frame(frame_a, "frame_a")
        prepared_b = self._prepare_dmd_frame(frame_b, "frame_b")
        input_end = time.perf_counter()

        self._upload_texture(self.texture_b, prepared_b)
        upload_b_end = time.perf_counter()
        self._upload_texture(self.texture_a, prepared_a)
        upload_a_end = time.perf_counter()

        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        self._draw_mirrored_texture(self.texture_b, 0, self.half_width)
        self._draw_mirrored_texture(self.texture_a, self.half_width, self.width)
        draw_end = time.perf_counter()

        glfw.swap_buffers(self.window)
        frame_end = time.perf_counter()
        
        # Check and record stutters
        if cadence_dt is not None and cadence_dt > self.expected_frame_time * 1.5:
            self.dropped_frames += 1
            if frame_end - self.last_stutter_log > 2.0:
                phases = {
                            'input': input_end - frame_start,
                            'upload_b': upload_b_end - input_end,
                            'upload_a': upload_a_end - upload_b_end,
                            'draw': draw_end - upload_a_end,
                            'swap': frame_end - draw_end,
                        }
                total = sum(phases.values())
                slow_phase, slow_duration = max(phases.items(), key=lambda item: item[1])
                logger.warning(
                    'Paired render stutter: dt=%.2fms, Input=%.2fms, Upload B=%.2fms, Upload A=%.2fms, Draw=%.2fms, Swap=%.2fms, Total=%.2fms, Target=%.2fms, Slow phase=%s (%.2fms), Dropped frames=%d.',
                    cadence_dt * 1000,
                    phases['input'] * 1000,
                    phases['upload_b'] * 1000,
                    phases['upload_a'] * 1000,
                    phases['draw'] * 1000,
                    phases['swap'] * 1000,
                    total * 1000,
                    self.expected_frame_time * 1000,
                    slow_phase,
                    slow_duration * 1000,
                    self.dropped_frames,
                )
                self.last_stutter_log = frame_end
        glfw.poll_events()

    def _prepare_dmd_frame(self, frame: RGBFrame, label: str) -> RGBFrame:
        """
        Validates shape and datatype of frame.

        Args:
            frame (RGBFrame): The frame to prepare for display.
            label (str): The label for the frame.

        Raises:
            ValueError: Raised if the frame does not meet the expected criteria.

        Returns:
            RGBFrame: The prepared frame.
        """
        # Type / rank / dtype first: a non-array or a non-uint8 frame must be
        # rejected here rather than reaching glTexSubImage2D as garbage bytes.
        _validate_rgb_frame(frame, label)
        if frame.shape != (self.height, self.half_width, 3):
            raise ValueError(f'{label} shape {frame.shape} does not match expected {self.height}x{self.half_width}x3')
        if frame.flags.c_contiguous:
            return frame
        return np.ascontiguousarray(frame)

    def _upload_texture(self, texture_id: int, frame: RGBFrame):
        """
        Uploads texture.

        Args:
            texture_id (int): Texture ID
            frame (RGBFrame): Frame
        """
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
        gl.glTexSubImage2D(
            gl.GL_TEXTURE_2D,
            0,
            0,
            0,
            self.half_width,
            self.height,
            gl.GL_RGB,
            gl.GL_UNSIGNED_BYTE,
            frame,
        )

    def _draw_mirrored_texture(self, texture_id: int, left: int, right: int):
        """
        Draws a mirrored texture.

        Args:
            texture_id (int): Texture ID
            left (int): Left coordinate
            right (int): Right coordinate
        """
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
        gl.glBegin(gl.GL_QUADS)
        gl.glTexCoord2f(1, 0)
        gl.glVertex2f(left, 0)
        gl.glTexCoord2f(0, 0)
        gl.glVertex2f(right, 0)
        gl.glTexCoord2f(0, 1)
        gl.glVertex2f(right, self.height)
        gl.glTexCoord2f(1, 1)
        gl.glVertex2f(left, self.height)
        gl.glEnd()

    def display_frame(self, frame: RGBFrame):
        """
        Display a precomposed B-left/A-right frame through the paired texture path.
        
        Args:
            frame (RGBFrame): The precomposed frame to display.
            """
        if frame.shape != (self.height, self.width, 3):
            logger.error('Paired frame shape %s does not match expected shape of %dx%d', frame.shape, self.height, self.width)
            raise ValueError(f'Paired frame shape {frame.shape} does not match excpected shape of {self.height}x{self.width}x3')
        frame_b = frame[:, :self.half_width, :]
        frame_a = frame[:, self.half_width:, :]
        self.display_pair(frame_a, frame_b)

    def should_close(self) -> bool:
        """
        Checks if window should close from GLFW or key press.

        Returns:
            bool: Should close (True) or not (False).
        """
        return glfw.window_should_close(self.window) or (glfw.get_key(self.window, glfw.KEY_ESCAPE) == glfw.PRESS)

    def cleanup(self):
        """
        Cleans up GLFW windows and textures.
        """
        try:
            if getattr(self, 'window', None):
                glfw.make_context_current(self.window)
                texture_ids = [
                    texture_id
                    for texture_id in (
                        getattr(self, 'texture_b', None),
                        getattr(self, 'texture_a', None),
                    )
                    if texture_id is not None
                ]
                if texture_ids and not getattr(self, '_textures_deleted', False):
                    gl.glDeleteTextures(texture_ids)
                    self._textures_deleted = True
                glfw.destroy_window(self.window)
        finally:
            glfw.terminate()
