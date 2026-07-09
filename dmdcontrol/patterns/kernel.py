"""Reusable 3x3 kernel frame helpers without OpenGL or USB imports."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple, TypedDict

import numpy as np

from dmdcontrol.patterns.bitplanes import BinaryMaskArray, RGBFrameArray
from dmdcontrol.support.constants import (
    BITPLANES,
    DMD_HEIGHT,
    DMD_WIDTH,
    INTER_PATTERN_DARK_US,
    SAFE_MARGIN_US,
)


class KernelLutOverride(NamedTuple):
    entries_count: int | None
    exposure_us: int | None


class KernelFrameMetadata(TypedDict):
    leader_frames: int
    payload_vsyncs: int
    blank_slot_count: int
    cycle_vsyncs: int
    cycle_fires: int
    black_frame: RGBFrameArray


class KernelFrameBuild(NamedTuple):
    frames: list[RGBFrameArray]
    metadata: KernelFrameMetadata


def compute_kernel_lut_override(
    enabled: bool,
    exposure_us: int | None = None,
    target_hz: float | None = None,
    sequence_utilization: float | None = None,
    dark_time_us: int | None = None,) -> KernelLutOverride:
    if not enabled or exposure_us is None:
        return KernelLutOverride(None, None)
    if target_hz is None or sequence_utilization is None:
        raise ValueError("target_hz and sequence_utilization are required when kernel override is enabled")
    frame_period_us = 1_000_000.0 / target_hz
    usable_us = (frame_period_us - SAFE_MARGIN_US) * sequence_utilization
    actual_dark_us = INTER_PATTERN_DARK_US if dark_time_us is None else dark_time_us
    entries_count = int(usable_us // (exposure_us + actual_dark_us))
    entries_count = max(1, min(BITPLANES, entries_count))
    return KernelLutOverride(entries_count, exposure_us)


def generate_kernel_masks(
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
    kernel_px: int = 30,) -> list[BinaryMaskArray]:
    """Generate 512 binary masks, one per 3x3 binary kernel variation."""
    if kernel_px % 3 != 0:
        raise ValueError(f"kernel_px ({kernel_px}) must be a multiple of 3")
    if kernel_px > min(width, height):
        raise ValueError(f"kernel_px ({kernel_px}) exceeds frame {width}x{height}")

    cell = kernel_px // 3
    x0 = (width - kernel_px) // 2
    y0 = (height - kernel_px) // 2
    masks: list[BinaryMaskArray] = []
    for kernel_index in range(512):
        mask = np.zeros((height, width), dtype=np.uint8)
        for bit in range(9):
            if kernel_index & (1 << bit):
                row, col = bit // 3, bit % 3
                yy, xx = y0 + row * cell, x0 + col * cell
                mask[yy:yy + cell, xx:xx + cell] = 1
        masks.append(mask)
    return masks


def pack_kernel_frames(
    engine: Any,
    masks: Sequence[BinaryMaskArray],
    slots_per_frame: int = BITPLANES,
    blank_end_frame: bool = False,) -> list[RGBFrameArray]:
    """Pack kernel masks into DisplayPort RGB frames consumed by the LUT."""
    if slots_per_frame < 1 or slots_per_frame > BITPLANES:
        raise ValueError(f"slots_per_frame ({slots_per_frame}) must be in [1, {BITPLANES}].")
    black_mask = np.zeros((engine.height, engine.width), dtype=np.uint8)
    pad = (-len(masks)) % slots_per_frame
    padded = list(masks) + [black_mask] * pad
    unused = [black_mask] * (BITPLANES - slots_per_frame)
    frames = [
        engine.pack_patterns(padded[i:i + slots_per_frame] + unused)
        for i in range(0, len(padded), slots_per_frame)]
    if blank_end_frame:
        frames.append(engine.pack_patterns([black_mask] * BITPLANES))
    return frames


def build_kernel_frames(
    engine: Any,
    kernel_px: int,
    slots_per_frame: int = BITPLANES,
    leader_frames: int = 3,
    blank_end_frame: bool = True,) -> KernelFrameBuild:
    if leader_frames < 0:
        raise ValueError("leader_frames must be non-negative")
    kernel_masks = generate_kernel_masks(engine.width, engine.height, kernel_px)
    black_frame = engine.pack_patterns(
        [np.zeros((engine.height,
                   engine.width),
                  dtype=np.uint8)] * BITPLANES)
    payload_frames = pack_kernel_frames(
        engine,
        kernel_masks,
        slots_per_frame=slots_per_frame,
        blank_end_frame=blank_end_frame,
    )
    frames = [black_frame] * leader_frames + payload_frames
    metadata = KernelFrameMetadata(
        leader_frames=leader_frames,
        payload_vsyncs=len(payload_frames),
        blank_slot_count=(slots_per_frame - (512 % slots_per_frame)) % slots_per_frame,
        cycle_vsyncs=len(frames),
        cycle_fires=(leader_frames * slots_per_frame) + 512 +
        ((slots_per_frame -
          (512 % slots_per_frame)) % slots_per_frame) + (slots_per_frame if blank_end_frame else 0),
        black_frame=black_frame,
    )
    return KernelFrameBuild(frames, metadata)


class KernelFrameProvider:

    def __init__(
        self,
        frames: Sequence[RGBFrameArray],
        black_frame: RGBFrameArray,
        single_shot: bool = False,) -> None:
        if not frames:
            raise ValueError("frames must not be empty")
        self._frames = frames
        self._black_frame = black_frame
        self._single_shot = single_shot
        self._index = 0

    def __call__(self) -> RGBFrameArray:
        index = self._index
        if self._single_shot and index >= len(self._frames):
            return self._black_frame
        self._index += 1
        return self._frames[index % len(self._frames)]
