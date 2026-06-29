from __future__ import annotations

import math

from dmdcontrol.patterns.paired import MAX_COUNT_SEQUENCE_FRAMES
from dmdcontrol.runtime.lifecycle import build_lut_entries
from dmdcontrol.support.constants import (
    BITPLANES,
    DEFAULT_HZ,
    DEFAULT_SEQUENCE_UTILIZATION,
)


class _DryRunDLPC:

    def get_display_dimensions(self):
        return None


def resolve_count_slots_per_frame(
    *,
    count_start: int,
    count_end: int,
    exposure_us: int | None,
    dark_time_us: int | None,
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
        try:
            build_lut_entries(
                _DryRunDLPC(),
                target_hz,
                sequence_utilization=utilization,
                entries_count=slots,
                per_entry_exposure_us=exposure_us,
                dark_time_us=dark_time_us,
            )
        except ValueError:
            continue
        return slots

    raise ValueError(
        "No valid --count-slots-per-frame can display "
        f"{count_start}..{count_end} with exposure={exposure_us or 'auto'}us, "
        f"dark={dark_time_us or 0}us, target_hz={target_hz}, "
        f"utilization={utilization}, and <= {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames.")
