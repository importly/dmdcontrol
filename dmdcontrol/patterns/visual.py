"""Human-visible RGB diagnostic patterns for tiny DMD optical images."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from dmdcontrol.support.constants import (
    DEFAULT_COARSE_GRID_SPACING,
    DEFAULT_COARSE_GRID_THICKNESS,
    DEFAULT_COARSE_LINE_SPACING,
    DEFAULT_COARSE_LINE_THICKNESS,
    DMD_HEIGHT,
    DMD_WIDTH,
)

RGBFrame = NDArray[np.uint8]


def _blank_rgb(width: int, height: int) -> RGBFrame:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    return np.zeros((height, width, 3), dtype=np.uint8)


def _validate_spacing(spacing: int, thickness: int) -> None:
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    if thickness <= 0:
        raise ValueError("thickness must be positive")


def _paint_vertical_bands(frame: RGBFrame, spacing: int, thickness: int, offset: int) -> None:
    width = frame.shape[1]
    x = offset % spacing
    while x < width:
        frame[:, x:min(width, x + thickness), :] = 255
        x += spacing


def _paint_horizontal_bands(frame: RGBFrame, spacing: int, thickness: int, offset: int) -> None:
    height = frame.shape[0]
    y = offset % spacing
    while y < height:
        frame[y:min(height, y + thickness), :, :] = 255
        y += spacing


def generate_coarse_grid_rgb(
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    spacing: int = DEFAULT_COARSE_GRID_SPACING,
    thickness: int = DEFAULT_COARSE_GRID_THICKNESS,
    offset_x: int = 0,
    offset_y: int = 0,) -> RGBFrame:
    """Return a binary RGB grid with human-scale spacing and thick strokes."""
    _validate_spacing(spacing, thickness)
    frame = _blank_rgb(width, height)
    _paint_vertical_bands(frame, spacing, thickness, offset_x)
    _paint_horizontal_bands(frame, spacing, thickness, offset_y)
    return np.ascontiguousarray(frame)


def generate_coarse_lines_rgb(
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    spacing: int = DEFAULT_COARSE_LINE_SPACING,
    thickness: int = DEFAULT_COARSE_LINE_THICKNESS,
    orientation: str = "vertical",
    offset: int = 0,) -> RGBFrame:
    """Return thick vertical or horizontal bands instead of one-pixel lines."""
    _validate_spacing(spacing, thickness)
    frame = _blank_rgb(width, height)
    if orientation == "vertical":
        _paint_vertical_bands(frame, spacing, thickness, offset)
    elif orientation == "horizontal":
        _paint_horizontal_bands(frame, spacing, thickness, offset)
    else:
        raise ValueError("orientation must be 'vertical' or 'horizontal'")
    return np.ascontiguousarray(frame)
