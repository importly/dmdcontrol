"""Paired A/B frames, their CPU patterns, and the OpenGL engine that shows both DMDs.

One 3840x1080 window spans both DisplayPort outputs: B (DP-0) is the left half, A (DP-4) the
right. Each half is one DMD image, mirrored horizontally for the optics. A half is either

- an RGB array (`RGBFrame`), uploaded to a texture every frame, or
- a `GpuPattern`, drawn straight on the GPU: the hook for shader-generated kernels.

DLPC900 Video Pattern Mode shows binary bitplanes taken from the RGB data; bitplane i lives at
`bitplane_location(i)` (G0..G7, R0..R7, B0..B7). The LUTs here only use bitplane 0 (G bit 0).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, Union

import glfw
import numpy as np
import OpenGL.GL as gl
from numpy.typing import NDArray

from dmdcontrol.patterns.bitplanes import bitplane_location
from dmdcontrol.patterns.modes import generate_decimal_number_rgb
from dmdcontrol.utils import CONFIG

logger = logging.getLogger('Paired')

DMD_WIDTH = int(CONFIG['DMD']['width'])
DMD_HEIGHT = int(CONFIG['DMD']['height'])
TARGET_HZ = int(CONFIG['DMD']['target_hz'])

RGBFrame = NDArray[np.uint8]


class GpuPattern(Protocol):
    """One DMD image drawn on the GPU instead of uploaded from an array, e.g. a shader-generated kernel.

    The engine calls draw() with the viewport set to that DMD's half of the window and a projection
    that maps (0, 0)..(1, 1) onto the DMD image (x right, y down) with the optical mirror applied,
    texturing off and the half already cleared to black. Draw in those units: a 1x1 kernel is a
    dot at (x / DMD_WIDTH, y / DMD_HEIGHT), landing where generate_dot_frame(x, y) would.
    """

    def draw(self) -> None: ...


Frame = Union[RGBFrame, GpuPattern]


@dataclass(frozen=True)
class FramePair:
    """What DMD A and DMD B show during one VSYNC."""

    a: Frame
    b: Frame


def as_frame_pair(value: FramePair | tuple[Frame, Frame]) -> FramePair:
    return value if isinstance(value, FramePair) else FramePair(*value)


class PairFrameProvider:
    """Hands the render thread the FramePair for each VSYNC."""

    def initial_pair(self) -> FramePair:
        raise NotImplementedError

    def next_pair(self) -> FramePair:
        raise NotImplementedError


# CPU patterns. These are the references a GPU version should match.

def bitplane_frame(mask: NDArray, bitplane: int = 0) -> RGBFrame:
    """RGB frame that shows a binary mask on one DLPC900 bitplane."""
    location = bitplane_location(bitplane)
    frame = np.zeros((*mask.shape, 3), dtype=np.uint8)
    frame[..., location.rgb_channel] = (mask != 0).astype(np.uint8) << location.bit
    return frame


def _decimal_number_display_masks(
    numbers: Iterable[int],
    *,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    size_px: int | None = None,
) -> list[NDArray[np.uint8]]:
    """Binary seven-segment mask for each number."""
    return [(generate_decimal_number_rgb(number, width=width, height=height, size_px=size_px)[:, :, 0] > 0)
            .astype(np.uint8) for number in numbers]


def generate_dot_frame(
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    x: float | None = None,
    y: float | None = None,
    radius: int = 40,
) -> RGBFrame:
    """White filled circle on black, on every bitplane: the single-dot (1x1) kernel."""
    x = width / 2 if x is None else x
    y = height / 2 if y is None else y
    yy, xx = np.ogrid[:height, :width]
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[(xx - x) ** 2 + (yy - y) ** 2 <= radius ** 2] = 255
    return frame


def checkerboard_frame(width: int = DMD_WIDTH, height: int = DMD_HEIGHT, block: int = 32) -> RGBFrame:
    yy, xx = np.indices((height, width))
    return np.repeat((((xx // block + yy // block) % 2) * 255).astype(np.uint8)[:, :, None], 3, axis=2)


def pack_count_sequence_frames(count_start: int, count_end: int, size_px: int | None = None) -> tuple[RGBFrame, ...]:
    """count_start, blank, count_start + 1, blank, ... on bitplane 0."""
    blank = np.zeros((DMD_HEIGHT, DMD_WIDTH, 3), dtype=np.uint8)
    frames: list[RGBFrame] = []
    for mask in _decimal_number_display_masks(range(count_start, count_end + 1), size_px=size_px):
        frames += [bitplane_frame(mask), blank]
    return tuple(frames)


def pack_sequence_frames(fm: np.ndarray) -> np.ndarray:
    """Four VSYNC frames per feature map: positive part, blank, positive part again, blank (bitplane 0)."""
    frames = np.zeros((len(fm) * 4, *fm.shape[1:], 3), dtype=np.uint8)
    for index, feature_map in enumerate(fm):
        frames[4 * index] = frames[4 * index + 2] = bitplane_frame(feature_map > 0)
    return frames


class PairedPatternEngine:
    """One undecorated 3840x1080 GLFW window: B on the left half, A on the right, one swap per VSYNC."""

    STREAM_TEXTURES = 4  # per DMD, rotated so an upload never waits on a texture the GPU is still drawing

    def __init__(self):
        self.half_width, self.height = DMD_WIDTH, DMD_HEIGHT
        self.width = 2 * self.half_width
        self.expected_frame_time = 1.0 / TARGET_HZ
        self.last_frame_time = 0.0
        self.dropped_frames = 0
        self.last_stutter_log = 0.0

        if not glfw.init():
            raise RuntimeError('Could not initialize GLFW')
        glfw.window_hint(glfw.DECORATED, glfw.FALSE)
        glfw.window_hint(glfw.RESIZABLE, glfw.FALSE)
        glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
        glfw.window_hint(glfw.REFRESH_RATE, TARGET_HZ)
        self.window = glfw.create_window(self.width, self.height, 'DLPC900 Paired Pattern Engine', None, None)
        if not self.window:
            glfw.terminate()
            raise RuntimeError('Could not create paired GLFW window')
        glfw.set_window_pos(self.window, 0, 0)
        glfw.make_context_current(self.window)
        glfw.swap_interval(1)

        fb_w, fb_h = glfw.get_framebuffer_size(self.window)
        logger.info('Paired framebuffer: %dx%d (requested %dx%d @ %dHz)', fb_w, fb_h, self.width, self.height, TARGET_HZ)
        if (fb_w, fb_h) != (self.width, self.height):
            glfw.terminate()
            raise RuntimeError(f'Paired framebuffer is {fb_w}x{fb_h}, expected {self.width}x{self.height}')

        # Each half draws in DMD units: (0, 0)..(1, 1), y down, x mirrored for the optics
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        gl.glOrtho(1, 0, 1, 0, -1, 1)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadIdentity()
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        gl.glTexEnvi(gl.GL_TEXTURE_ENV, gl.GL_TEXTURE_ENV_MODE, gl.GL_REPLACE)  # ignore any glColor a pattern left
        self._textures = {side: [self._new_texture() for _ in range(self.STREAM_TEXTURES)] for side in 'ab'}
        self._slot = 0

    def make_context_current(self):
        glfw.make_context_current(self.window)

    def release_context(self):
        glfw.make_context_current(None)  # pyright: ignore

    def reset_cadence(self) -> None:
        """Forget the last frame time so a phase change is not counted as a stutter."""
        self.last_frame_time = 0.0

    def display_pair(self, frame_a: Frame, frame_b: Frame) -> None:
        start = time.perf_counter()
        cadence_dt = start - self.last_frame_time if self.last_frame_time else None
        self.last_frame_time = start
        self._slot = (self._slot + 1) % self.STREAM_TEXTURES

        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        self._draw_half(frame_b, 0, self._textures['b'][self._slot])                # left, DP-0
        self._draw_half(frame_a, self.half_width, self._textures['a'][self._slot])  # right, DP-4
        drawn = time.perf_counter()
        glfw.swap_buffers(self.window)

        if cadence_dt is not None and cadence_dt > 1.5 * self.expected_frame_time:
            self.dropped_frames += 1
            now = time.perf_counter()
            if now - self.last_stutter_log > 2.0:
                logger.warning('Paired render stutter: dt=%.2fms (draw %.2fms, swap %.2fms), dropped frames=%d',
                               cadence_dt * 1e3, (drawn - start) * 1e3, (now - drawn) * 1e3, self.dropped_frames)
                self.last_stutter_log = now

    def _draw_half(self, frame: Frame, x0: int, texture: int) -> None:
        gl.glViewport(x0, 0, self.half_width, self.height)
        if not isinstance(frame, np.ndarray):
            frame.draw()
            return
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
        gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, 0, 0, self.half_width, self.height,
                           gl.GL_RGB, gl.GL_UNSIGNED_BYTE, np.ascontiguousarray(frame))
        gl.glBegin(gl.GL_QUADS)
        for x, y in ((0, 0), (1, 0), (1, 1), (0, 1)):
            gl.glTexCoord2f(x, y)
            gl.glVertex2f(x, y)
        gl.glEnd()
        gl.glDisable(gl.GL_TEXTURE_2D)

    def _new_texture(self) -> int:
        texture = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB8, self.half_width, self.height, 0,
                        gl.GL_RGB, gl.GL_UNSIGNED_BYTE, None)
        return texture

    def cleanup(self):
        glfw.make_context_current(self.window)
        gl.glDeleteTextures([texture for textures in self._textures.values() for texture in textures])
        glfw.destroy_window(self.window)
        glfw.terminate()
