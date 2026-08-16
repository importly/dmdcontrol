from __future__ import annotations

import math
from argparse import Namespace
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Literal, TypedDict, overload

from dmdcontrol.patterns.paired import (
    MAX_COUNT_SEQUENCE_FRAMES,
    count_lut_entries_per_frame,
)
from dmdcontrol.runtime.lut import LutTimingMetadata, build_lut_entries
from dmdcontrol.utils import CONFIG

ArgsNamespace = Namespace | SimpleNamespace

BITPLANES = CONFIG.get('DMD', {}).get('bitplanes')


class CountSequenceMetadata(TypedDict):
    count_start: int
    count_end: int
    count_slots_per_frame: int
    count_slots_per_frame_mode: str
    count_blank_between_frames: bool
    count_blank_after_each_count: bool
    count_lut_entries_per_frame: int


class CountPairPreviewMetadata(TypedDict):
    start: int
    end: int
    slots_per_frame: int
    slots_per_frame_mode: str
    blank_between_frames: bool
    blank_after_each_count: bool
    lut_entries_per_frame: int


@dataclass(frozen=True)
class CountSequenceConfig:
    """Semantic count recipe before it is converted to source frames and LUT slots.

    The semantic display order is count, optional blank, count, optional blank,
    ... after any pre-semantic startup triggers are skipped. Count/blank mode
    intentionally uses one semantic item per RGB source frame so it does not
    rely on multiple DLPC900 bitplanes from the same live video frame.
    """

    count_start: int
    count_end: int
    count_slots_per_frame: int
    count_blank_between_frames: bool = False
    count_slots_per_frame_mode: str = "explicit"

    @classmethod
    @overload
    def from_args(
        cls,
        args: ArgsNamespace,
        *,
        require_resolved_slots: Literal[True] = True,) -> CountSequenceConfig:
        ...

    @classmethod
    @overload
    def from_args(
        cls,
        args: ArgsNamespace,
        *,
        require_resolved_slots: Literal[False],) -> "CountSequenceConfig | None":
        ...

    @classmethod
    def from_args(
        cls,
        args: ArgsNamespace,
        *,
        require_resolved_slots: bool = True,) -> "CountSequenceConfig | None":
        slots = getattr(args, "count_slots_per_frame", None)
        if slots is None:
            if require_resolved_slots:
                raise ValueError("--count-slots-per-frame auto did not resolve")
            return None
        count_start = getattr(args, "count_start", 1)
        count_end = getattr(args, "count_end", count_start + int(slots) - 1)
        return cls(
            count_start=count_start,
            count_end=count_end,
            count_slots_per_frame=slots,
            count_blank_between_frames=getattr(args, "count_blank_between_frames", False),
            count_slots_per_frame_mode=getattr(args, "count_slots_per_frame_mode", "explicit"),
        )

    @property
    def count_total(self) -> int:
        return self.count_end - self.count_start + 1

    @property
    def lut_entries_per_frame(self) -> int:
        return count_lut_entries_per_frame(
            self.count_slots_per_frame,
            count_blank_between_frames=self.count_blank_between_frames,
        )

    @property
    def frame_count(self) -> int:
        if self.count_blank_between_frames:
            return self.count_total * 2
        return self.count_total // self.count_slots_per_frame

    @property
    def expected_trigger_count(self) -> int:
        return self.count_total * (2 if self.count_blank_between_frames else 1)

    @property
    def blank_lut_entries_per_frame(self) -> int:
        return 0

    def validate_shape(self, *, max_frames: int = MAX_COUNT_SEQUENCE_FRAMES) -> None:
        if self.count_start > self.count_end:
            raise ValueError("Run.count_start must be <= Run.count_end")
        if self.count_slots_per_frame <= 0 or self.count_slots_per_frame > BITPLANES:
            raise ValueError(f"Run.count_slots_per_frame must be in the range 1..{BITPLANES}")
        if self.count_blank_between_frames and self.count_slots_per_frame != 1:
            raise ValueError(
                "Run.count_blank_after_each_count requires Run.count_slots_per_frame 1 "
                "so each count and blank uses its own RGB source frame.")
        if self.lut_entries_per_frame > BITPLANES:
            raise ValueError(
                f"Run.count_slots_per_frame {self.count_slots_per_frame} with "
                f"Run.count_blank_after_each_count needs {self.lut_entries_per_frame} "
                f"LUT entries; max is {BITPLANES}")
        if not self.count_blank_between_frames and self.count_total % self.count_slots_per_frame != 0:
            raise ValueError("count range length must be divisible by Run.count_slots_per_frame")
        if self.frame_count > max_frames:
            raise ValueError(f"a-count-b-static can span at most {max_frames} VSYNC frames")

    def validate_timing(self, *, exposure_us: int) -> LutTimingMetadata:
        return validate_count_lut_sequence_timing(
            count_slots_per_frame=self.count_slots_per_frame,
            exposure_us=exposure_us,
            count_blank_between_frames=self.count_blank_between_frames,
        )

    def to_metadata(self) -> CountSequenceMetadata:
        return {
            "count_start": self.count_start,
            "count_end": self.count_end,
            "count_slots_per_frame": self.count_slots_per_frame,
            "count_slots_per_frame_mode": self.count_slots_per_frame_mode,
            "count_blank_between_frames": self.count_blank_between_frames,
            "count_blank_after_each_count": self.count_blank_between_frames,
            "count_lut_entries_per_frame": self.lut_entries_per_frame,
        }

    def to_pair_preview_metadata(self) -> CountPairPreviewMetadata:
        return {
            "start": self.count_start,
            "end": self.count_end,
            "slots_per_frame": self.count_slots_per_frame,
            "slots_per_frame_mode": self.count_slots_per_frame_mode,
            "blank_between_frames": self.count_blank_between_frames,
            "blank_after_each_count": self.count_blank_between_frames,
            "lut_entries_per_frame": self.lut_entries_per_frame,
        }


def validate_count_lut_sequence_timing(
    *,
    count_slots_per_frame: int,
    exposure_us: int,
    count_blank_between_frames: bool = False,) -> LutTimingMetadata:
    # target_hz, frame_utilization, and dark_time_us are read from CONFIG by
    # build_lut_entries — they are no longer per-call overrides.
    if exposure_us is None:
        raise ValueError("DMD.exposure_us is required for count LUT timing")
    entries_count = count_lut_entries_per_frame(
        count_slots_per_frame,
        count_blank_between_frames=count_blank_between_frames,
    )
    _entries, timing = build_lut_entries(
        entries_count=entries_count,
        per_entry_exposure_us=exposure_us,
    )
    return timing


def resolve_count_slots_per_frame(
    *,
    count_start: int,
    count_end: int,
    exposure_us: int,
    count_blank_between_frames: bool = False,) -> int:
    if exposure_us is None:
        raise ValueError("DMD.exposure_us is required to resolve count LUT slots")
    if count_start > count_end:
        raise ValueError("Run.count_start must be <= Run.count_end")

    count_total = count_end - count_start + 1
    if count_blank_between_frames:
        validate_count_lut_sequence_timing(
            count_slots_per_frame=1,
            exposure_us=exposure_us,
            count_blank_between_frames=True,
        )
        if count_total * 2 > MAX_COUNT_SEQUENCE_FRAMES:
            raise ValueError(
                "No valid Run.count_slots_per_frame can display "
                f"{count_start}..{count_end} with blank frames because it needs "
                f"{count_total * 2} RGB source frames; max is {MAX_COUNT_SEQUENCE_FRAMES}.")
        return 1

    min_slots = max(1, math.ceil(count_total / MAX_COUNT_SEQUENCE_FRAMES))

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
            validate_count_lut_sequence_timing(
                count_slots_per_frame=slots,
                exposure_us=exposure_us,
                count_blank_between_frames=count_blank_between_frames,
            )
        except ValueError:
            continue
        return slots

    dmd = CONFIG.get('DMD', {})
    raise ValueError(
        "No valid Run.count_slots_per_frame can display "
        f"{count_start}..{count_end} with exposure={exposure_us or 'auto'}us, "
        f"dark={dmd.get('dark_time_us')}us, target_hz={dmd.get('target_hz')}, "
        f"utilization={dmd.get('frame_utilization')}, and <= {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames.")
