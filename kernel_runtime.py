"""Reusable 3x3 kernel frame helpers without OpenGL or USB imports."""

from __future__ import annotations

import numpy as np

from config import BITPLANES, SAFE_MARGIN_US


def compute_kernel_lut_override(
    enabled,
    kernel_exposure_us,
    target_hz,
    sequence_utilization,
):
    if not enabled or kernel_exposure_us is None:
        return None, None
    frame_period_us = 1_000_000.0 / target_hz
    usable_us = (frame_period_us - SAFE_MARGIN_US) * sequence_utilization
    entries_count = int(usable_us // kernel_exposure_us)
    entries_count = max(1, min(BITPLANES, entries_count))
    return entries_count, kernel_exposure_us


def generate_kernel_masks(width=1920, height=1080, kernel_px=30):
    """Generate 512 binary masks, one per 3x3 binary kernel variation."""
    if kernel_px % 3 != 0:
        raise ValueError(f"kernel_px ({kernel_px}) must be a multiple of 3")
    if kernel_px > min(width, height):
        raise ValueError(f"kernel_px ({kernel_px}) exceeds frame {width}x{height}")

    cell = kernel_px // 3
    x0 = (width - kernel_px) // 2
    y0 = (height - kernel_px) // 2
    masks = []
    for kernel_index in range(512):
        mask = np.zeros((height, width), dtype=np.uint8)
        for bit in range(9):
            if kernel_index & (1 << bit):
                row, col = bit // 3, bit % 3
                yy, xx = y0 + row * cell, x0 + col * cell
                mask[yy : yy + cell, xx : xx + cell] = 1
        masks.append(mask)
    return masks


def pack_kernel_frames(engine, masks, slots_per_frame=BITPLANES, blank_end_frame=False):
    """Pack kernel masks into DisplayPort RGB frames consumed by the LUT."""
    if slots_per_frame < 1 or slots_per_frame > BITPLANES:
        raise ValueError(
            f"slots_per_frame ({slots_per_frame}) must be in [1, {BITPLANES}]."
        )
    black_mask = np.zeros((engine.height, engine.width), dtype=np.uint8)
    pad = (-len(masks)) % slots_per_frame
    padded = list(masks) + [black_mask] * pad
    unused = [black_mask] * (BITPLANES - slots_per_frame)
    frames = [
        engine.pack_patterns(padded[i : i + slots_per_frame] + unused)
        for i in range(0, len(padded), slots_per_frame)
    ]
    if blank_end_frame:
        frames.append(engine.pack_patterns([black_mask] * BITPLANES))
    return frames


def build_kernel_frames(
    engine,
    kernel_px,
    slots_per_frame=BITPLANES,
    leader_frames=3,
    blank_end_frame=True,
):
    if leader_frames < 0:
        raise ValueError("leader_frames must be non-negative")
    kernel_masks = generate_kernel_masks(engine.width, engine.height, kernel_px)
    black_frame = engine.pack_patterns(
        [np.zeros((engine.height, engine.width), dtype=np.uint8)] * BITPLANES
    )
    payload_frames = pack_kernel_frames(
        engine,
        kernel_masks,
        slots_per_frame=slots_per_frame,
        blank_end_frame=blank_end_frame,
    )
    frames = [black_frame] * leader_frames + payload_frames
    metadata = {
        "leader_frames": leader_frames,
        "payload_vsyncs": len(payload_frames),
        "blank_slot_count": (slots_per_frame - (512 % slots_per_frame))
        % slots_per_frame,
        "cycle_vsyncs": len(frames),
        "cycle_fires": (leader_frames * slots_per_frame)
        + 512
        + ((slots_per_frame - (512 % slots_per_frame)) % slots_per_frame)
        + (slots_per_frame if blank_end_frame else 0),
        "black_frame": black_frame,
    }
    return frames, metadata


class KernelFrameProvider:
    def __init__(self, frames, black_frame, single_shot=False):
        if not frames:
            raise ValueError("frames must not be empty")
        self._frames = frames
        self._black_frame = black_frame
        self._single_shot = single_shot
        self._index = 0

    def __call__(self):
        index = self._index
        if self._single_shot and index >= len(self._frames):
            return self._black_frame
        self._index += 1
        return self._frames[index % len(self._frames)]
