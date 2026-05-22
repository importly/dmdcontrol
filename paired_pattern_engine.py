"""Paired 3840x1080 frame composition and OpenGL presentation."""

from __future__ import annotations

import importlib
import time
from dataclasses import dataclass

import numpy as np

from logger import logger

DMD_WIDTH = 1920
DMD_HEIGHT = 1080
PAIR_WIDTH = DMD_WIDTH * 2
PAIR_HEIGHT = DMD_HEIGHT
OFFSET_B = (0, 0)
OFFSET_A = (DMD_WIDTH, 0)

STATIC_PAIR_TESTS = ("checkerboard", "lines", "colors")
DYNAMIC_PAIR_TESTS = ("gradient", "snake")
PAIR_TESTS = STATIC_PAIR_TESTS + DYNAMIC_PAIR_TESTS


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


def _route_mark(frame, label):
    marked = frame.copy()
    height, width = marked.shape[:2]
    band_h = 1 if height < 32 else max(4, height // 80)
    marked[:band_h, :, :] = 0
    if label == "A":
        marked[:band_h, :, 0] = 255
        x0 = max(1, width // 32)
        y0 = max(1, height // 32)
        w = 1 if min(width, height) < 32 else max(4, width // 32)
        h = 1 if height < 32 else max(4, height // 8)
        h = min(h, max(1, height - y0))
        marked[y0 : y0 + h, x0 : x0 + w, 0] = 255
        marked[y0 : y0 + h, x0 + 2 * w : x0 + 3 * w, 0] = 255
        marked[y0 : y0 + w, x0 : x0 + 3 * w, 0] = 255
        marked[y0 + h // 2 : y0 + h // 2 + w, x0 : x0 + 3 * w, 0] = 255
    else:
        marked[:band_h, :, 1] = 255
        x0 = max(1, width // 32)
        y0 = max(1, height // 32)
        w = 1 if min(width, height) < 32 else max(4, width // 32)
        h = 1 if height < 32 else max(4, height // 8)
        h = min(h, max(1, height - y0))
        marked[y0 : y0 + h, x0 : x0 + w, 1] = 255
        marked[y0 : y0 + h, x0 + 2 * w : x0 + 3 * w, 1] = 255
        marked[y0 : y0 + w, x0 : x0 + 3 * w, 1] = 255
        marked[y0 + h // 2 : y0 + h // 2 + w, x0 : x0 + 3 * w, 1] = 255
        marked[y0 + h - w : y0 + h, x0 : x0 + 3 * w, 1] = 255
    return marked


def _static_frame(mode, width, height, route_label):
    if mode == "checkerboard":
        frame = _checkerboard(width, height)
    elif mode == "lines":
        frame = _lines(width, height)
    elif mode == "colors":
        frame = _colors(width, height, channel=0 if route_label == "A" else 1)
    else:
        raise ValueError(f"Unsupported static pair mode: {mode}")
    return _route_mark(frame, route_label)


class PairFrameProvider:
    def initial_pair(self):
        raise NotImplementedError

    def next_pair(self):
        raise NotImplementedError


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


class DynamicGradientPairFrameProvider(PairFrameProvider):
    def __init__(self, width=DMD_WIDTH, height=DMD_HEIGHT):
        self.width = width
        self.height = height
        self.frame_index = 0

    def _frame_for_index(self, index):
        x = np.arange(self.width, dtype=np.uint16)[None, :]
        y = np.arange(self.height, dtype=np.uint16)[:, None]
        base = ((x + index * 7) % 256).astype(np.uint8)
        vertical = ((y * 255) // max(1, self.height - 1)).astype(np.uint8)

        frame_a = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame_b = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame_a[:, :, 0] = base
        frame_a[:, :, 2] = vertical
        frame_b[:, :, 1] = base
        frame_b[:, :, 2] = 255 - vertical
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
        for route, frame, channel in (("A", frame_a, 0), ("B", frame_b, 1)):
            offset = 0 if route == "A" else self.cells_x // 2
            for segment in range(6):
                pos = (head - segment + offset) % path_len
                row = pos // self.cells_x
                col = pos % self.cells_x
                x0 = col * cell_w
                y0 = row * cell_h
                level = max(64, 255 - segment * 32)
                frame[y0 : y0 + cell_h, x0 : x0 + cell_w, channel] = level
        return _route_mark(frame_a, "A"), _route_mark(frame_b, "B")

    def initial_pair(self):
        return self._frame_for_index(self.frame_index)

    def next_pair(self):
        self.frame_index += 1
        return self._frame_for_index(self.frame_index)


def make_pair_frame_provider(test, test_a=None, test_b=None, width=DMD_WIDTH, height=DMD_HEIGHT):
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
    raise ValueError(f"Unsupported paired test mode: {test}")


def _load_gl_modules():
    glfw = importlib.import_module("glfw")
    gl = importlib.import_module("OpenGL.GL")
    return glfw, gl


class PairedPatternEngine:
    def __init__(self, width=PAIR_WIDTH, height=PAIR_HEIGHT, fps=60, x=0, y=0):
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
