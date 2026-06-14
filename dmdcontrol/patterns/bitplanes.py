from __future__ import annotations

import numpy as np

from dmdcontrol.support.constants import BITPLANES


def pack_bitplanes_rgb(binary_images, width, height):
    if len(binary_images) != BITPLANES:
        raise ValueError(f"expected {BITPLANES} binary images, got {len(binary_images)}")
    red = np.zeros((height, width), dtype=np.uint8)
    green = np.zeros((height, width), dtype=np.uint8)
    blue = np.zeros((height, width), dtype=np.uint8)
    for bit in range(8):
        green |= np.asarray(binary_images[bit], dtype=np.uint8) << bit
        red |= np.asarray(binary_images[bit + 8], dtype=np.uint8) << bit
        blue |= np.asarray(binary_images[bit + 16], dtype=np.uint8) << bit
    return np.ascontiguousarray(np.stack([red, green, blue], axis=-1))


def unpack_rgb_bitplanes(rgb_array, width, height):
    if rgb_array.shape[:2] != (height, width):
        raise ValueError(f"RGB array must be {height}x{width}, got {rgb_array.shape[:2]}")
    patterns = []
    for bit in range(8):
        patterns.append(((rgb_array[:, :, 1] >> bit) & 1).astype(np.uint8))
    for bit in range(8):
        patterns.append(((rgb_array[:, :, 0] >> bit) & 1).astype(np.uint8))
    for bit in range(8):
        patterns.append(((rgb_array[:, :, 2] >> bit) & 1).astype(np.uint8))
    return patterns
