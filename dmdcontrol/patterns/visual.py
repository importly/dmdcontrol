"""Human-visible RGB diagnostic patterns for tiny DMD optical images."""

from __future__ import annotations

import numpy as np

DEFAULT_COARSE_GRID_SPACING = 75
DEFAULT_COARSE_GRID_THICKNESS = 8
DEFAULT_COARSE_LINE_SPACING = 150
DEFAULT_COARSE_LINE_THICKNESS = 24
DEFAULT_ROUTE_MARKER_SIZE = 168


def _blank_rgb(width, height):
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    return np.zeros((height, width, 3), dtype=np.uint8)


def _validate_spacing(spacing, thickness):
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    if thickness <= 0:
        raise ValueError("thickness must be positive")


def _paint_vertical_bands(frame, spacing, thickness, offset):
    width = frame.shape[1]
    x = offset % spacing
    while x < width:
        frame[:, x: min(width, x + thickness), :] = 255
        x += spacing


def _paint_horizontal_bands(frame, spacing, thickness, offset):
    height = frame.shape[0]
    y = offset % spacing
    while y < height:
        frame[y: min(height, y + thickness), :, :] = 255
        y += spacing


def generate_coarse_grid_rgb(
        width=1920,
        height=1080,
        spacing=DEFAULT_COARSE_GRID_SPACING,
        thickness=DEFAULT_COARSE_GRID_THICKNESS,
        offset_x=0,
        offset_y=0,
):
    """Return a binary RGB grid with human-scale spacing and thick strokes."""
    _validate_spacing(spacing, thickness)
    frame = _blank_rgb(width, height)
    _paint_vertical_bands(frame, spacing, thickness, offset_x)
    _paint_horizontal_bands(frame, spacing, thickness, offset_y)
    return np.ascontiguousarray(frame)


def generate_coarse_lines_rgb(
        width=1920,
        height=1080,
        spacing=DEFAULT_COARSE_LINE_SPACING,
        thickness=DEFAULT_COARSE_LINE_THICKNESS,
        orientation="vertical",
        offset=0,
):
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
