from __future__ import annotations

import math

from dmdcontrol.patterns.paired import MAX_COUNT_SEQUENCE_FRAMES, count_lut_entries_per_frame
from dmdcontrol.runtime.lifecycle import build_lut_entries
from dmdcontrol.support.constants import (
    BITPLANES,
    DEFAULT_HZ,
    DEFAULT_SEQUENCE_UTILIZATION,
)


class _DryRunDLPC:

    def get_display_dimensions(self):
        return None


def validate_count_lut_sequence_does_not_repeat(
    *,
    count_slots_per_frame: int,
    exposure_us: int | None,
    dark_time_us: int | None,
    count_blank_between_frames: bool = False,
    target_hz: float = DEFAULT_HZ,
    sequence_utilization: float | None = DEFAULT_SEQUENCE_UTILIZATION,
) -> dict:
    utilization = (
        DEFAULT_SEQUENCE_UTILIZATION
        if sequence_utilization is None else sequence_utilization)
    entries_count = count_lut_entries_per_frame(
        count_slots_per_frame,
        count_blank_between_frames=count_blank_between_frames,
    )
    _entries, timing = build_lut_entries(
        _DryRunDLPC(),
        target_hz,
        sequence_utilization=utilization,
        entries_count=entries_count,
        per_entry_exposure_us=exposure_us,
        dark_time_us=dark_time_us,
    )
    if timing["total_sequence_us"] * 2 <= timing["frame_period_us"]:
        raise ValueError(
            "Count-mode LUT sequence is short enough to repeat before the next VSYNC "
            f"({timing['total_sequence_us']:.1f} us sequence in a "
            f"{timing['frame_period_us']:.1f} us frame). Increase "
            "--count-slots-per-frame or omit it to use auto; for "
            "--exposure-us 4000 with --count-blank-between-frames, use "
            "--count-slots-per-frame 2.")
    return timing


def resolve_count_slots_per_frame(
    *,
    count_start: int,
    count_end: int,
    exposure_us: int | None,
    dark_time_us: int | None,
    count_blank_between_frames: bool = False,
    target_hz: float = DEFAULT_HZ,
    sequence_utilization: float | None = DEFAULT_SEQUENCE_UTILIZATION,
) -> int:
    if count_start > count_end:
        raise ValueError("--count-start must be <= --count-end")

    count_total = count_end - count_start + 1
    min_slots = max(1, math.ceil(count_total / MAX_COUNT_SEQUENCE_FRAMES))
    utilization = (
        DEFAULT_SEQUENCE_UTILIZATION
        if sequence_utilization is None else sequence_utilization)

    for slots in range(BITPLANES, min_slots - 1, -1):
        if count_total % slots != 0:
            continue
        entries_count = count_lut_entries_per_frame(
            slots,
            count_blank_between_frames=count_blank_between_frames,
        )
        if entries_count > BITPLANES:
            continue
        try:
            validate_count_lut_sequence_does_not_repeat(
                count_slots_per_frame=slots,
                exposure_us=exposure_us,
                dark_time_us=dark_time_us,
                count_blank_between_frames=count_blank_between_frames,
                target_hz=target_hz,
                sequence_utilization=utilization,
            )
        except ValueError:
            continue
        return slots

    raise ValueError(
        "No valid --count-slots-per-frame can display "
        f"{count_start}..{count_end} with exposure={exposure_us or 'auto'}us, "
        f"dark={dark_time_us or 0}us, target_hz={target_hz}, "
        f"utilization={utilization}, and <= {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames.")
