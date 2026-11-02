"""GpuPattern generators: patterns drawn on the GPU instead of uploaded as full 1920x1080 RGB frames.

A full RGB frame costs a 6 MB upload per DMD per VSYNC; these upload at most the pattern's own
pixels, so a sequence of hundreds of different patterns needs neither gigabytes of frames nor
most of the frame time for uploads.
"""

from __future__ import annotations

import numpy as np
import OpenGL.GL as gl
from numpy.typing import NDArray

from dmdcontrol.utils import CONFIG

DMD_WIDTH = CONFIG.DMD.width
DMD_HEIGHT = CONFIG.DMD.height


class BlankPattern:
    """Nothing lit: the engine has already cleared the half to black."""

    def draw(self) -> None:
        pass


BLANK = BlankPattern()


class MaskPattern:
    """A binary mask at its own size (1 mask pixel = 1 DMD pixel), centred on the DMD, lit on every bitplane.

    Lands pixel for pixel where bitplane_frame() of the same mask centred in a full frame would.
    The texture is made, filled and deleted inside each draw(), so the pattern holds no GL state
    and works in any engine.
    """

    def __init__(self, mask: NDArray, width: int = DMD_WIDTH, height: int = DMD_HEIGHT):
        h, w = mask.shape
        if h > height or w > width:
            raise ValueError(f'mask {w}x{h} is larger than the DMD ({width}x{height})')
        self.rgb = np.ascontiguousarray(np.repeat(np.where(mask != 0, 255, 0).astype(np.uint8)[:, :, None], 3, axis=2))
        x0, y0 = (width - w) // 2, (height - h) // 2
        self.corners = (x0 / width, y0 / height, (x0 + w) / width, (y0 + h) / height)

    def draw(self) -> None:
        h, w = self.rgb.shape[:2]
        x0, y0, x1, y1 = self.corners
        texture = gl.glGenTextures(1)
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB8, w, h, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, self.rgb)
        gl.glBegin(gl.GL_QUADS)
        for (u, v), (x, y) in zip(((0, 0), (1, 0), (1, 1), (0, 1)), ((x0, y0), (x1, y0), (x1, y1), (x0, y1))):
            gl.glTexCoord2f(u, v)
            gl.glVertex2f(x, y)
        gl.glEnd()
        gl.glDisable(gl.GL_TEXTURE_2D)
        gl.glDeleteTextures([texture])
