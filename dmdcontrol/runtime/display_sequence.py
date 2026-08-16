"""Common paired display sequence model.

The paired pipeline intentionally has one ownership point for timing now:

1. Pattern adapters build ordinary RGB `FramePair` images.
2. Each RGB image packs one or more semantic masks into selected bitplanes.
3. Each `LutSlot` points at one packed bitplane and defines exposure, dark time,
   trigger enablement, and a human-readable semantic label.
4. The paired runtime loads an explicit LUT plan for each DLPC900 board. Modes
   with a static B aperture can hold B continuously while A keeps its own timing,
   and renders a sequence-backed cursor for prebuilt modes, so displayed frames
   and LUT timing cannot drift into separate interpretations.

For count/blank mode, each count and each blank gets its own source RGB frame
and one LUT entry. The timeline is `1, blank, 2, blank, ...` without relying on
multiple selected bitplanes from the same live RGB frame.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, TypedDict
import logging

import numpy as np

from dmdcontrol.patterns.paired import (
    FramePair,
    PairFrameProvider,
    generate_static_frame,
    pack_count_sequence_frames,
)
from dmdcontrol.patterns import pack_sequence_frames, pack_static_frames
from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.lut import LutEntry, LutTimingMetadata, build_lut_entries
from dmdcontrol.patterns import FramePair, PairFrameProvider, pack_sequence_frames, pack_static_frames
from dmdcontrol.utils import CONFIG

logger = logging.getLogger('DisplaySequence')

class StartupLeaderMetadata(TypedDict):
    leader_vsyncs: int
    trigger_count: int
    entries_count: int
    trig2_mode: str
    frame_role: str
    startup_policy: str
    startup_leader_trigger_count: int
    phase_guard_trigger_count: int


class LutSlotMetadata(TypedDict):
    bitplane_index: int
    exposure_us: int
    dark_us: int
    trig2_enabled: bool
    clear_after: bool
    semantic_role: str
    semantic_label: str | None
    wait_for_trigger: bool


class TimedFramePairMetadata(TypedDict):
    source_frame_index: int
    semantic_labels: list[str]
    lut_slots: list[LutSlotMetadata]


class DisplaySequenceMetadata(TypedDict):
    source_frame_count: int
    lut_slots_per_source_frame: int
    repeat: bool
    target_hz: float
    expected_trigger_count: int
    startup_policy: str
    startup_leader: StartupLeaderMetadata
    frames: list[TimedFramePairMetadata]


@dataclass(frozen=True)
class LutSlot:
    """One DLPC900 LUT entry plus the semantic bitplane it displays."""

    bitplane_index: int
    exposure_us: int
    dark_us: int
    trig2_enabled: bool
    clear_after: bool
    semantic_role: str
    semantic_label: str | None = None
    wait_for_trigger: bool = False

    def to_lut_entry(
        self,
        *,
        pattern_index: int | None = None,
        wait_for_trigger: bool | None = None,
    ) -> LutEntry:
        bit_position = int(self.bitplane_index)
        frame_change = (
            self.wait_for_trigger if wait_for_trigger is None else wait_for_trigger
        )
        return LutEntry(
            pattern_index=bit_position if pattern_index is None else int(pattern_index),
            exposure_us=int(self.exposure_us),
            clear_after=bool(self.clear_after),
            bit_depth=1,
            led_select=7,
            dark_us=int(self.dark_us),
            trig2_disabled=not bool(self.trig2_enabled),
            bit_position=bit_position,
            image_pattern_index=0,
            wait_for_trigger=bool(frame_change),
        )


@dataclass(frozen=True)
class TimedFramePair:
    """One source RGB frame pair and the LUT slots that consume its bitplanes."""

    frame_pair: FramePair
    lut_slots: tuple[LutSlot, ...]
    source_frame_index: int
    semantic_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class StartupPolicy:
    """How the render coordinator bridges from pre-start frames to semantic frames."""

    mode: Literal["blank_leader", "prime_first_frame"]
    leader_vsyncs: int = 0
    frame_role: str = "blank_pair"


@dataclass(frozen=True)
class DmdLutPlan:
    """Controller-specific LUT contract for one side of a paired display."""

    entries: tuple[LutEntry, ...]
    timing: LutTimingMetadata
    role: str = "semantic"


@dataclass(frozen=True)
class PairedDisplaySequence:
    """Complete frame/timing contract consumed by paired runtime and metadata."""

    frames: tuple[TimedFramePair, ...]
    startup_policy: StartupPolicy
    repeat: bool
    target_hz: float
    timing: LutTimingMetadata
    mode_metadata: dict[str, object] = field(default_factory=dict)
    provider: PairFrameProvider | None = None
    startup_pair: FramePair | None = None
    b_lut_plan: DmdLutPlan | None = None

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("PairedDisplaySequence requires at least one frame")
        slot_count = len(self.frames[0].lut_slots)
        if slot_count <= 0:
            raise ValueError(
                "PairedDisplaySequence frames require at least one LUT slot"
            )
        for frame in self.frames:
            if len(frame.lut_slots) != slot_count:
                raise ValueError("all source frames must use the same LUT slot count")

    @property
    def lut_slots(self) -> tuple[LutSlot, ...]:
        return self.frames[0].lut_slots

    def lut_entries(self) -> list[LutEntry]:
        return [
            slot.to_lut_entry(pattern_index=index)
            for index, slot in enumerate(self.lut_slots)
        ]

    def lut_plan_a(self) -> DmdLutPlan:
        return DmdLutPlan(
            entries=tuple(self.lut_entries()),
            timing=self.timing,
            role="semantic",
        )

    def lut_plan_b(self) -> DmdLutPlan:
        return self.b_lut_plan or self.lut_plan_a()

    def startup_leader_metadata(self) -> StartupLeaderMetadata:
        entries_count = len(self.lut_slots)
        leader_vsyncs = int(self.startup_policy.leader_vsyncs)
        startup_leader_trigger_count = 0
        if self.startup_policy.mode == "blank_leader":
            startup_leader_trigger_count = (
                leader_vsyncs
                if self.timing.get("trig2_mode") == "frame_zero"
                else leader_vsyncs * entries_count
            )
        phase_guard_trigger_count = self._phase_guard_trigger_count()
        return {
            "leader_vsyncs": leader_vsyncs,
            "trigger_count": int(
                startup_leader_trigger_count + phase_guard_trigger_count
            ),
            "entries_count": entries_count,
            "trig2_mode": str(self.timing.get("trig2_mode") or "per_bitplane"),
            "frame_role": (
                "blank_phase_guard"
                if phase_guard_trigger_count and not startup_leader_trigger_count
                else self.startup_policy.frame_role
            ),
            "startup_policy": self.startup_policy.mode,
            "startup_leader_trigger_count": int(startup_leader_trigger_count),
            "phase_guard_trigger_count": int(phase_guard_trigger_count),
        }

    def _phase_guard_trigger_count(self) -> int:
        if self.startup_policy.mode != "prime_first_frame" or not self.lut_slots:
            return 0
        first_slot = self.lut_slots[0]
        if first_slot.semantic_role == "blank" and first_slot.trig2_enabled:
            return 1
        return 0

    def metadata(self) -> DisplaySequenceMetadata:
        """Describe the frame/LUT pairing without exposing image arrays.

        Each source RGB frame owns one fixed set of LUT slots. The runtime uses
        this record for capture metadata so the camera side can distinguish
        semantic source frames from any startup frames emitted before the DLPC
        sequencers begin.
        """
        return {
            "source_frame_count": len(self.frames),
            "lut_slots_per_source_frame": len(self.lut_slots),
            "repeat": bool(self.repeat),
            "target_hz": float(self.target_hz),
            "expected_trigger_count": self.expected_trigger_count(),
            "startup_policy": self.startup_policy.mode,
            "startup_leader": self.startup_leader_metadata(),
            "frames": [
                {
                    "source_frame_index": int(frame.source_frame_index),
                    "semantic_labels": list(frame.semantic_labels),
                    "lut_slots": [
                        {
                            "bitplane_index": int(slot.bitplane_index),
                            "exposure_us": int(slot.exposure_us),
                            "dark_us": int(slot.dark_us),
                            "trig2_enabled": bool(slot.trig2_enabled),
                            "clear_after": bool(slot.clear_after),
                            "semantic_role": slot.semantic_role,
                            "semantic_label": slot.semantic_label,
                            "wait_for_trigger": bool(slot.wait_for_trigger),
                        }
                        for slot in frame.lut_slots
                    ],
                }
                for frame in self.frames
            ],
        }

    def expected_trigger_count(self) -> int:
        return sum(
            1 for frame in self.frames for slot in frame.lut_slots if slot.trig2_enabled
        )


class FrameSequenceProvider(PairFrameProvider):
    """Deterministic runtime cursor over `PairedDisplaySequence.frames`."""

    def __init__(
        self,
        frames: tuple[TimedFramePair, ...],
        *,
        repeat: bool,
        terminal_pair: FramePair | None = None,
    ) -> None:
        if not frames:
            raise ValueError("FrameSequenceProvider requires at least one frame")
        self._frames = tuple(frames)
        self.repeat = bool(repeat)
        self._terminal_pair = terminal_pair
        self.frame_index = 0
        self._next_index = 0

    def initial_pair(self) -> FramePair:
        self.frame_index = 0
        self._next_index = 1
        return self._frames[0].frame_pair

    def next_pair(self) -> FramePair:
        if self._next_index >= len(self._frames):
            if self.repeat:
                self._next_index = 0
            elif self._terminal_pair is not None:
                self.frame_index = len(self._frames)
                return self._terminal_pair
            else:
                self._next_index = len(self._frames) - 1

        self.frame_index = self._next_index
        self._next_index += 1
        return self._frames[self.frame_index].frame_pair

def build_dynamic_fm_sequence(
    fm: np.ndarray,
    k: np.ndarray,
) -> PairedDisplaySequence:
    # Build LUT entries and slots for one frame
    entries, timing = build_lut_entries(
        clear_last_after_exposure=True
    )
    base_slots = _slots_from_lut_entries(entries, semantic_role="frame")

    frames_a = pack_sequence_frames(fm)
    frames_b = pack_static_frames(
        data = k,
        batch_size = len(frames_a),
        pos = True,
    )
    # Match A's already-resolved exposure instead of filling B to the
    # nominal VSYNC budget. The latter is fragile when the controller's
    # measured VSYNC is a fraction faster than the requested refresh rate.
    # B still remains continuously visible because clear_after is false.
    entries_b, timing_b = build_lut_entries(
        trig2_frame_zero=True,
        clear_last_after_exposure=False,
    )
    frames: list[TimedFramePair] = []

    base_slot = base_slots[0]
    for source_frame_index, frame_a in enumerate(frames_a):
        labels = [f"frame:{source_frame_index}"]

        frames.append(
            TimedFramePair(
                frame_pair=FramePair(a=frame_a, b=frames_b[source_frame_index]),
                lut_slots=_slots_with_labels((base_slot,), labels),
                source_frame_index=source_frame_index,
                semantic_labels=tuple(labels),
            )
        )

    startup_policy = StartupPolicy(
        "blank_leader",
        CONFIG.get('DMD', {}).get('paired_startup_leader_vsyncs', 16),
        frame_role="a_blank_b_static",
    )
    startup_pair = FramePair(a=np.zeros((CONFIG.get('DMD', {}).get('height', 1080), CONFIG.get('DMD', {}).get('width', 1920), 3), dtype=np.uint8), b=frames_b[0])
    frame_tuple = tuple(frames)
    return PairedDisplaySequence(
        frames=frame_tuple,
        startup_policy=startup_policy,
        repeat=True,
        target_hz=CONFIG.get('DMD', {}).get('target_hz', 60.0),
        timing=timing,
        mode_metadata={
            "count": {
                "exposure_us": CONFIG.get('DMD', {}).get('exposure_us'),
            },
            "static_b": {
                "continuous_hold": True,
                "dark_time_us": 0,
                "trigger_source_for_camera": "A",
            },
        },
        provider=FrameSequenceProvider(frame_tuple, repeat=True),
        startup_pair=startup_pair, # blank start up sequence frames
        b_lut_plan=DmdLutPlan(tuple(entries_b), timing_b, role="static_hold"),
    )


def build_count_static_sequence() -> PairedDisplaySequence:
    """Build the count/blank A-side vs static B-side, doing it here instead of main because there is more dmd setup happening than actual high level stuff"""
    run = CONFIG.get('Run', {})
    dmd = CONFIG.get('DMD', {})
    width = int(dmd.get('width', 1920))
    height = int(dmd.get('height', 1080))
    target_hz = float(dmd.get('target_hz', 60.0))

    count_config = CountSequenceConfig.from_run_config()
    entries, timing = build_lut_entries(
        entries_count=count_config.lut_entries_per_frame,
    )
    base_slots = _slots_from_lut_entries(entries, semantic_role="count")

    # count mode owns its frame packing here so LUT slots and RGB bitplanes are built together.
    frames_a = pack_count_sequence_frames(
        count_config.count_start,
        count_config.count_end,
        count_config.count_slots_per_frame,
        width=width,
        height=height,
        size_px=run.get('number_size_px'),
        count_blank_between_frames=count_config.count_blank_between_frames,
    )
    frame_b = generate_static_frame(
        run.get('test_b', 'dot'),
        width=width,
        height=height,
        route_label="B",
        dot_x=run.get('b_dot_x'),
        dot_y=run.get('b_dot_y'),
        dot_radius=run.get('b_dot_radius'),
    )
    # B holds one continuously visible pattern
    entries_b, timing_b = build_lut_entries(
        entries_count=1,
        clear_last_after_exposure=False,
        trig2_frame_zero=True,
    )

    frames: list[TimedFramePair] = []
    counts = tuple(range(count_config.count_start, count_config.count_end + 1))
    if count_config.count_blank_between_frames:
        if len(base_slots) != 1:
            raise ValueError(
                "count blank insertion expects one LUT slot per source frame"
            )
        base_slot = base_slots[0]
        for source_frame_index, frame_a in enumerate(frames_a):
            if source_frame_index % 2 == 0:
                count = counts[source_frame_index // 2]
                labels = [f"count:{count}"]
            else:
                labels = ["blank"]
            frames.append(
                TimedFramePair(
                    frame_pair=FramePair(a=frame_a, b=frame_b),
                    lut_slots=_slots_with_labels((base_slot,), labels),
                    source_frame_index=source_frame_index,
                    semantic_labels=tuple(labels),
                )
            )
    else:
        for source_frame_index, (frame_a, offset) in enumerate(
            zip(frames_a, range(0, len(counts), count_config.count_slots_per_frame))
        ):
            labels = _count_slot_labels(
                counts[offset : offset + count_config.count_slots_per_frame],
                blank_after_each_count=False,
            )
            frames.append(
                TimedFramePair(
                    frame_pair=FramePair(a=frame_a, b=frame_b),
                    lut_slots=_slots_with_labels(base_slots, labels),
                    source_frame_index=source_frame_index,
                    semantic_labels=tuple(
                        label for label in labels if label != "blank"
                    ),
                )
            )

    startup_policy = StartupPolicy(
        "blank_leader",
        int(dmd.get('paired_startup_leader_vsyncs', 16)),
        frame_role="a_blank_b_static",
    )
    startup_pair = FramePair(a=np.zeros((height, width, 3), dtype=np.uint8), b=frame_b)
    frame_tuple = tuple(frames)
    return PairedDisplaySequence(
        frames=frame_tuple,
        startup_policy=startup_policy,
        repeat=True,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={
            "count": {
                **count_config.to_pair_preview_metadata(),
                "exposure_us": timing["exposure_us"],
            },
            "static_b": {
                "continuous_hold": True,
                "dark_time_us": 0,
                "trigger_source_for_camera": "A",
            },
        },
        provider=FrameSequenceProvider(frame_tuple, repeat=True),
        startup_pair=startup_pair,
        b_lut_plan=DmdLutPlan(tuple(entries_b), timing_b, role="static_hold"),
    )


def _slots_from_lut_entries(
    entries: Iterable[LutEntry],
    *,
    semantic_role: str,
) -> tuple[LutSlot, ...]:
    slots: list[LutSlot] = []
    for entry in entries:
        slots.append(
            LutSlot(
                bitplane_index=int(entry.bit_position),
                exposure_us=int(entry.exposure_us),
                dark_us=int(entry.dark_us),
                trig2_enabled=not bool(entry.trig2_disabled),
                clear_after=bool(entry.clear_after),
                semantic_role=semantic_role,
                wait_for_trigger=bool(entry.wait_for_trigger),
            )
        )
    return tuple(slots)


def _slots_with_labels(
    slots: tuple[LutSlot, ...], labels: list[str]
) -> tuple[LutSlot, ...]:
    if len(slots) != len(labels):
        raise ValueError("LUT slot labels must match LUT slot count")
    labeled = []
    for slot, label in zip(slots, labels):
        labeled.append(
            LutSlot(
                bitplane_index=slot.bitplane_index,
                exposure_us=slot.exposure_us,
                dark_us=slot.dark_us,
                trig2_enabled=slot.trig2_enabled,
                clear_after=slot.clear_after,
                semantic_role="blank" if label == "blank" else slot.semantic_role,
                semantic_label=label,
                wait_for_trigger=bool(slot.wait_for_trigger),
            )
        )
    return tuple(labeled)


def _count_slot_labels(
    counts: Iterable[int], *, blank_after_each_count: bool
) -> list[str]:
    labels: list[str] = []
    for count in counts:
        labels.append(f"count:{count}")
        if blank_after_each_count:
            labels.append("blank")
    return labels
