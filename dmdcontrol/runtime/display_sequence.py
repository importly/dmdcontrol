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
from typing import Literal, TypedDict, NotRequired
import logging
import math

import numpy as np

from dmdcontrol.patterns import (
    FramePair,
    PairFrameProvider,
    count_lut_entries_per_frame,
    generate_static_frame,
    pack_count_sequence_frames,
    pack_sequence_frames,
    pack_static_frames,
)
# from dmdcontrol.runtime.lut import LutEntry, LutTimingMetadata, build_lut_entries
from dmdcontrol.utils import CONFIG

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from typing import TYPE_CHECKING, Callable

from dmdcontrol.dmd import (
    _bit6_is_cosmetic,
    _format_hw,
    ensure_video_pattern_mode,
    wait_for_external_lock,
    wait_for_stable_external_lock,
    wait_for_sequencer_running,
)

if TYPE_CHECKING:
    from dmdcontrol.dmd import DLPC900

BITPLANES = CONFIG.get('DMD', {}).get('bitplanes')
MAX_COUNT_SEQUENCE_FRAMES = CONFIG.get('DMD', {}).get('max_count_sequence_frames', 128)

logger = logging.getLogger('DisplaySequence')

class StartupLeaderMetadata(TypedDict):
    vsyncs: int
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
class LutEntry:
    pattern_index: int
    exposure_us: int
    clear_after: bool
    bit_depth: int
    led_select: int
    dark_us: int
    trig2_disabled: bool
    bit_position: int
    image_pattern_index: int = 0
    wait_for_trigger: bool = False

    @property
    def bitplane_index(self) -> int:
        """Selected video bit/frame position; kept as a compatibility alias."""
        return self.bit_position


class TriggerOutTiming(TypedDict):
    channel: str
    edge: str
    rising_delay_us: int
    falling_delay_us: int
    pulse_width_us: int


class LutTimingMetadata(TypedDict):
    timing_source: str
    sequence_utilization: float
    frame_period_us: float
    safe_frame_period_us: float
    usable_frame_period_us: float
    safe_margin_us: float
    measured_frame_hz: float | None
    effective_frame_hz: float
    requested_binary_rate_hz: float
    effective_binary_rate_hz: float
    exposure_us: int
    dark_us: int
    total_sequence_us: float
    idle_headroom_us: float
    entries_count: int
    clear_last_after_exposure: NotRequired[bool]
    hold_last_pattern_until_vsync: NotRequired[bool]
    trigger_out_2: NotRequired[TriggerOutTiming]


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
    provider: PairFrameProvider
    startup_pair: FramePair
    mode_metadata: dict[str, object] = field(default_factory=dict)
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
            "vsyncs": leader_vsyncs,
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
    entries, base_slots, timing = build_lut_entries(
        clear_last_after_exposure=True
    )
    
    # Count mode owns its frame packing here so LUT slots and RGB bitplanes are built together.
    frames_a = pack_sequence_frames(fm)
    frame_b = pack_static_frames(
        data = k,
        batch_size = len(frames_a),
        pos = True,
    )
    # Match A's already-resolved exposure instead of filling B to the
    # nominal VSYNC budget. The latter is fragile when the controller's
    # measured VSYNC is a fraction faster than the requested refresh rate.
    # B still remains continuously visible because clear_after is false.
    entries_b, _, timing_b = build_lut_entries(
        trig2_frame_zero=True,
        clear_last_after_exposure=False,
    )
    frames: list[TimedFramePair] = []

    base_slot = base_slots[0]
    for source_frame_index, frame_a in enumerate(frames_a):
        labels = [f"frame:{source_frame_index}"]

        frames.append(
            TimedFramePair(
                frame_pair=FramePair(a=frame_a, b=frame_b),
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
    startup_pair = FramePair(a=np.zeros((CONFIG.get('DMD', {}).get('height', 1080), CONFIG.get('DMD', {}).get('width', 1920), 3), dtype=np.uint8), b=frame_b)
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
    _, base_slots, timing = build_lut_entries()

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
    # this used to have entries_count=1 in it
    entries_b, _, timing_b = build_lut_entries(
        clear_last_after_exposure=False,
        trig2_frame_zero=True,
    )

    frames: list[TimedFramePair] = []
    counts = tuple(range(count_config.count_start, count_config.count_end + 1))
    # if count_config.count_blank_between_frames:
    # if len(base_slots) != 1:
    #     raise ValueError(
    #         "count blank insertion expects one LUT slot per source frame"
    #     )
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
    # else:
    #     for source_frame_index, (frame_a, offset) in enumerate(
    #         zip(frames_a, range(0, len(counts), count_config.count_slots_per_frame))
    #     ):
    #         labels = _count_slot_labels(
    #             counts[offset : offset + count_config.count_slots_per_frame],
    #             blank_after_each_count=False,
    #         )
    #         frames.append(
    #             TimedFramePair(
    #                 frame_pair=FramePair(a=frame_a, b=frame_b),
    #                 lut_slots=_slots_with_labels(base_slots, labels),
    #                 source_frame_index=source_frame_index,
    #                 semantic_labels=tuple(
    #                     label for label in labels if label != "blank"
    #                 ),
    #             )
    #         )

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


def build_lut_entries(
    clear_last_after_exposure: bool = True,
    trig2_frame_zero: bool = False,
    ) -> tuple[list[LutEntry], tuple[LutSlot, ...], LutTimingMetadata]:
    """
    Builds the LUT entries for each bitplane

    Args:
        clear_last_after_exposure (bool, optional): wheter to clear the last entry after each exposure. Defaults to True.
        trig2_frame_zero (bool, optional): whether to enable trig2 for the first frame. Defaults to False.

    Returns:
        tuple[list[LutEntry], tuple[LutSlot], LutTimingMetadata]: list of LutEntry, list of LutSlot, and LutTimingMetadata
    """
    dmd = CONFIG.get('DMD', {})
    target_hz = float(dmd.get('target_hz'))
    bitplanes = dmd.get('bitplanes')
    per_entry_exposure_us = int(dmd.get('exposure_us'))
    min_exposure_us = dmd.get('min_exposure_us')
    safe_margin_us = dmd.get('safe_margin_us')
    dark_time_us = dmd.get('dark_time_us')
    frame_utilization = dmd.get('frame_utilization')
    max_binary_rate_hz = dmd.get('max_binary_rate_hz')
    max_vsync_deviation_ratio = dmd.get('max_vsync_deviation_ratio')

    measured_frame_hz = None
    total_pixels = int(dmd.get('total_pixels_per_line')) * int(dmd.get('total_lines_per_frame'))
    pixel_clock_hz = int(dmd.get('pixel_clock_khz')) * 1000
    if total_pixels > 0 and pixel_clock_hz > 0:
        measured_frame_hz = pixel_clock_hz / total_pixels

    if measured_frame_hz is not None:
        rel_err = abs(measured_frame_hz - target_hz) / target_hz
        if rel_err > max_vsync_deviation_ratio:
            logger.warning(
                "Ignoring unstable measured VSYNC %.3f Hz (target %.3f Hz, deviation %.1f%%). "
                "Using target Hz for LUT timing. Display dims at measurement: total=%sx%s, active=%sx%s, pclk=%skHz",
                measured_frame_hz,
                target_hz,
                rel_err * 100.0,
                dmd.get('total_pixels_per_line'),
                dmd.get('total_lines_per_frame'),
                dmd.get('active_pixels_per_line'),
                dmd.get('active_lines_per_frame'),
                dmd.get('pixel_clock_khz'),
            )
            measured_frame_hz = None

    effective_frame_hz = measured_frame_hz if measured_frame_hz else target_hz
    timing_source = 'measured' if measured_frame_hz else 'target_fallback'
    frame_period_us = 1000000.0 / effective_frame_hz
    safe_frame_period_us = frame_period_us - safe_margin_us
    if safe_frame_period_us <= 0:
        logger.error('Frame period %.2f us is not larger than safety margin %.2f us.', frame_period_us, safe_margin_us)
        raise ValueError(
            f"Frame period {frame_period_us:.2f} us is not larger than safety margin {safe_margin_us:.2f} us."
        )

    usable_frame_period_us = safe_frame_period_us * frame_utilization

    if per_entry_exposure_us < min_exposure_us:
        logger.error('exposure_us (%s) is below the configured minimum (%s).', per_entry_exposure_us, min_exposure_us)
        raise ValueError(f'exposure_us ({per_entry_exposure_us}) is below the configured minimum ({min_exposure_us}).')

    # Fit as many entries as the exposure allows within the frame budget.
    requested_segment_us = per_entry_exposure_us + dark_time_us
    entries_count = int(usable_frame_period_us // requested_segment_us)
    entries_count = max(1, min(bitplanes, entries_count))

    requested_binary_rate_hz = target_hz * entries_count
    if requested_binary_rate_hz > max_binary_rate_hz:
        logger.error('Requested binary rate %.1f Hz exceeds DLP6500 1-bit limit (~%.1f Hz).', requested_binary_rate_hz, max_binary_rate_hz,)
        raise ValueError(f'Requested binary rate {requested_binary_rate_hz:.1f} Hz exceeds DLP6500 1-bit limit (~{max_binary_rate_hz} Hz).')

    effective_binary_rate_hz = effective_frame_hz * entries_count
    if effective_binary_rate_hz > max_binary_rate_hz:
        logger.error('Measured source binary rate %.1f Hz exceeds DLP6500 1-bit limit (~%.1f Hz).', effective_binary_rate_hz, max_binary_rate_hz,)
        raise ValueError(f'Measured source binary rate {effective_binary_rate_hz:.1f} Hz exceeds DLP6500 1-bit limit (~{max_binary_rate_hz} Hz).')

    total_sequence_us = requested_segment_us * entries_count
    if total_sequence_us > usable_frame_period_us:
        logger.error('%d LUT entries at %d us exposure need %.1f us per VSYNC but only %.1f us is usable.', entries_count, per_entry_exposure_us, total_sequence_us, usable_frame_period_us)
        raise ValueError(f'{entries_count} LUT entries at {per_entry_exposure_us} us exposure need {total_sequence_us:.1f} us per VSYNC but only {usable_frame_period_us:.1f} us is usable.')

    idle_headroom_us = frame_period_us - total_sequence_us

    entries: list[LutEntry] = []
    base_slots: list[LutSlot] = []
    for bit_pos in range(entries_count):
        trig2_disable = (bit_pos != 0) if trig2_frame_zero else False
        clear_flag = bool(clear_last_after_exposure and bit_pos == (entries_count - 1))
        entries.append(
            LutEntry(
                pattern_index=bit_pos,
                exposure_us=per_entry_exposure_us,
                clear_after=clear_flag,
                bit_depth=1,
                led_select=7,
                dark_us=dark_time_us,
                trig2_disabled=trig2_disable,
                bit_position=bit_pos,
                image_pattern_index=0,
                wait_for_trigger=(bit_pos == 0),
            )
        )
        base_slots.append(
            LutSlot(
                bitplane_index=bit_pos,
                exposure_us=per_entry_exposure_us,
                dark_us=int(dark_time_us),
                trig2_enabled=not trig2_disable,
                clear_after=clear_flag,
                semantic_role='count',
                wait_for_trigger=bool(bit_pos == 0),
            )
        )
        
    timing: LutTimingMetadata = {
        "timing_source": timing_source,
        "sequence_utilization": frame_utilization,
        "frame_period_us": frame_period_us,
        "safe_frame_period_us": safe_frame_period_us,
        "usable_frame_period_us": usable_frame_period_us,
        "safe_margin_us": safe_margin_us,
        "measured_frame_hz": measured_frame_hz,
        "effective_frame_hz": effective_frame_hz,
        "requested_binary_rate_hz": requested_binary_rate_hz,
        "effective_binary_rate_hz": effective_binary_rate_hz,
        "exposure_us": per_entry_exposure_us,
        "dark_us": dark_time_us,
        "total_sequence_us": total_sequence_us,
        "idle_headroom_us": idle_headroom_us,
        "entries_count": entries_count,
        "clear_last_after_exposure": bool(clear_last_after_exposure),
        "hold_last_pattern_until_vsync": not bool(clear_last_after_exposure),
    }
    return entries, tuple(base_slots), timing


def compute_trigger_out_2_timing() -> TriggerOutTiming:
    pulse_width_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('pulse_width_us'))
    rising_delay_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('rising_delay_us'))
    falling_delay_us = rising_delay_us + pulse_width_us
    
    delay_max_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('delay_max_us'))
    delay_min_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('delay_min_us'))
    max_rising_delay_us = delay_max_us - pulse_width_us
    
    if rising_delay_us < delay_min_us or rising_delay_us > max_rising_delay_us:
        raise ValueError(f'rising_delay_us must be between {delay_min_us} and {max_rising_delay_us}')
    if falling_delay_us < delay_min_us or falling_delay_us > delay_max_us:
        raise ValueError(f'falling_delay_us must be between {delay_min_us} and {delay_max_us}')
    
    return {
        'channel': 'TRIG_OUT_2',
        'edge': 'rising',
        'rising_delay_us': rising_delay_us,
        'falling_delay_us': falling_delay_us,
        'pulse_width_us': pulse_width_us,
    }


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
    def from_run_config(cls) -> CountSequenceConfig:
        """Build and validate the count recipe from the `Run`/`DMD` config sections."""
        run = CONFIG.get('Run', {})
        exposure_us = int(CONFIG.get('DMD', {}).get('exposure_us'))
        count_start = int(run.get('count_start'))
        count_end = int(run.get('count_end'))
        count_blank_between_frames = bool(run.get('count_blank_after_each_count'))

        slots_raw = run.get('count_slots_per_frame')
        if isinstance(slots_raw, str):
            if slots_raw.strip().lower() != 'auto':
                raise ValueError(
                    "Run.count_slots_per_frame must be a positive integer or 'auto', "
                    f"got {slots_raw!r}")
            slots = resolve_count_slots_per_frame(
                count_start=count_start,
                count_end=count_end,
                exposure_us=exposure_us,
                count_blank_between_frames=count_blank_between_frames,
            )
            slots_mode = "auto"
        else:
            slots = int(slots_raw)
            slots_mode = "explicit"

        config = cls(
            count_start=count_start,
            count_end=count_end,
            count_slots_per_frame=slots,
            count_blank_between_frames=count_blank_between_frames,
            count_slots_per_frame_mode=slots_mode,
        )
        config.validate_shape()
        config.validate_timing(exposure_us=exposure_us)
        return config

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

    def validate_shape(self, *, max_frames: int = CONFIG.get("DMD", {}).get("max_count_sequence_frames", 128)) -> None:
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
    _, _,  timing = build_lut_entries()
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


@dataclass
class PreparedSequenceState:
    entries: list[LutEntry]
    timing: LutTimingMetadata

def load_pattern_sequence(dlpc: DLPC900, entries: Sequence[LutEntry]) -> None:
    # DLPU018J §2.4.4.3.4: Pattern Display LUT Reorder (0x1A32) is "only applicable
    # in Pre-stored Pattern Mode and Pattern On-The-Fly Mode" — NOT Video Pattern Mode.

    # Pre-LUT snapshot. If ABORT is already set here, the latch is sticky from
    # a prior boot/run — distinguishes "we caused it" from "it was already there".
    hw_pre = dlpc.get_hardware_status()
    logger.debug(f"  [arm] hw pre-LUT  = {_format_hw(hw_pre)}")

    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(len(entries), repeat=True)
    hw_after_lut = dlpc.get_hardware_status()
    logger.debug(f"  [arm] hw post-LUT = {_format_hw(hw_after_lut)}")


def start_loaded_pattern_sequence(
    dlpc: DLPC900,
    post_start_delay_s: float = 0.2,) -> None:
    dlpc.start_pattern_display(2)
    if post_start_delay_s > 0:
        time.sleep(post_start_delay_s)


def start_loaded_pattern_sequences(
    dlpc_a: DLPC900,
    dlpc_b: DLPC900,
    post_start_delay_s: float = 0.2,
    verify: bool = False,) -> None:
    barrier = threading.Barrier(3)
    errors: list[tuple[str, BaseException]] = []

    def _start_one(label: str, dlpc: DLPC900) -> None:
        try:
            barrier.wait()
            dlpc.start_pattern_display(2)
        except Exception as exc:
            errors.append((label, exc))

    threads = [
        threading.Thread(target=_start_one,
                         args=("A",
                               dlpc_a),
                         daemon=True),
        threading.Thread(target=_start_one,
                         args=("B",
                               dlpc_b),
                         daemon=True),
    ]
    for thread in threads:
        thread.start()

    barrier.wait()
    for thread in threads:
        thread.join()

    if errors:
        detail = "; ".join(f"{label}: {exc}" for label, exc in errors)
        raise RuntimeError(f"Paired sequencer start failed: {detail}")

    if post_start_delay_s > 0:
        time.sleep(post_start_delay_s)

    if verify:
        verify_started_pattern_sequence(dlpc_a, label="DMD A")
        verify_started_pattern_sequence(dlpc_b, label="DMD B")


def verify_started_pattern_sequence(
    dlpc: DLPC900,
    label: str = "DLPC900",) -> int | None:
    if not ensure_video_pattern_mode(dlpc, retries=2, poll_timeout_s=1.0):
        mode, _ = dlpc.get_display_mode()
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            f"{label} dropped out of Video Pattern Mode after sequencer start. "
            f"Mode readback: {mode}, main status: {ms}.")

    if not wait_for_sequencer_running(dlpc, timeout_s=1.5):
        ms = dlpc.get_main_status() or {}
        hw = dlpc.get_hardware_status()
        raise RuntimeError(
            f"{label} pattern sequencer did not report running after start command. "
            f"Main status: {ms}, hardware status: {hw}.")

    hw = dlpc.get_hardware_status()
    if hw is not None and (hw & 0x80):
        logger.warning(
            f"{label} hardware status sequence-error bit set (hw=0x{hw:02X}). "
            "Sequencer has reported a runtime error condition.")
    elif hw is not None and (hw & 0x40):
        logger.debug(
            f"  {label} post-config hw=0x{hw:02X}. "
            "Bit 6 latched (cosmetic, set by Pattern Stop).")
    return hw


def prepare_dlpc900_for_video_pattern(
    dlpc: DLPC900,
    entries_count: int | None = None,) -> PreparedSequenceState:
    # Note: dark_time_us (config) does not produce visible off-time in DLPC900 Video
    # Pattern Mode — use explicit blank frames or blank bitplanes. It is carried
    # through only for LUT timing/budget accounting.
    dmd_width = CONFIG.get('DMD', {}).get('width')
    dmd_height = CONFIG.get('DMD', {}).get('height')
    target_hz = CONFIG.get('DMD', {}).get('target_hz')
    dual_pixel = CONFIG.get('DMD', {}).get('dual_pixel')
    actual_entries = (entries_count if entries_count is not None
                      else CONFIG.get('DMD', {}).get('bitplanes'))
    logger.info(
        f"[+] Configuring DLPC900 for {dmd_width}x{dmd_height} @ {target_hz}Hz Video Pattern Mode "
        f"({actual_entries} LUT entr{'y' if actual_entries == 1 else 'ies'} per VSYNC)...")


    hw_first = dlpc.get_hardware_status()
    err0_code = dlpc.get_last_error()
    err0_desc = dlpc.get_error_description()
    logger.info(
        f"[+] DLPC900 first-touch status: hw={_format_hw(hw_first)} "
        f"last_err={err0_code!r} desc={err0_desc!r}")

    # Stop pattern display ONLY if currently in Pattern Mode (2). At boot the
    # display mode defaults to 0 (Video Mode) and Pattern Stop is firmware-NACKed,
    # producing harmless but noisy WARNING. Skip the unconditional stop.
    current_mode, _ = dlpc.get_display_mode()
    if current_mode == 2:
        logger.debug(
            f"  - Pre-config stop: display already in mode {current_mode}, sending Pattern Stop...")
        dlpc.start_pattern_display(0)
        time.sleep(0.2)
    else:
        logger.debug(
            f"  - Pre-config stop skipped (display mode={current_mode}, no pattern running).")

    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    #  must enter Video Mode (0) with desired source BEFORE switching to Mode 2.
    logger.debug("  - Entering Video Mode (0) with DisplayPort source...")
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)
    logger.debug("  - Setting input pixel format to RGB888 (0)...")
    dlpc.set_input_pixel_format(0)
    logger.debug("  - Setting EVM input channel swap ABC->BAC on Port 1...")
    dlpc.set_data_channel_swap(0, 4)
    dlpc.toggle_dual_pixel_mode(bool(dual_pixel))
    logger.info(f"[+] Parallel input pixel mode: {'Dual P1-P2' if dual_pixel else 'Single P1'}")

    # Force full active area — otherwise DLPC900 may use a stale Flash-resident crop.
    logger.debug(f"  - Forcing Input Display Resolution to {dmd_width}x{dmd_height}...")
    dlpc.set_input_display_resolution(0, 0, dmd_width, dmd_height)

    dlpc.apply_block_lock_workaround()

    logger.info("[+] Waiting for external source sync lock...")
    if wait_for_external_lock(dlpc, timeout_s=4.0):
        logger.info(
            "[+] External source lock acquired. Verifying stable video input (up to 3s)..."
        )
        if wait_for_stable_external_lock(
            dlpc,
            timeout_s=3.0,
            stable_for_s=0.25,
            required_mode=0,
        ):
            logger.info("[+] Video input is stable; continuing without the remaining dwell.")
        else:
            logger.warning(
                "Video input did not remain continuously stable during the 3s buffer timeout; "
                "continuing after the bounded fallback."
            )
    else:
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "External source sync lock was not acquired. "
            f"Main status: {ms}. Without lock, Video Pattern Mode and trigger outputs are unreliable."
        )

    # Per DLPU018J p.56: mode transition ~300ms. TI ref GUI uses 500ms.
    logger.debug("  - Switching to Video Pattern Mode (0x02)...")
    dlpc.set_display_mode(0x02)
    logger.debug("  - Waiting 500ms for mode transition...")
    time.sleep(0.5)

    # Stop before park: required in Video Pattern Mode or firmware latches abort bit 0x40.
    dlpc.start_pattern_display(0)
    time.sleep(0.05)
    dlpc.apply_block_lock_workaround()
    time.sleep(0.1)

    mode, _ = dlpc.get_display_mode()
    logger.debug(f"  - Display mode readback: {mode} (expected: 2)")

    if not ensure_video_pattern_mode(dlpc, retries=3, poll_timeout_s=1.5):
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "Failed to enter Video Pattern Mode (mode 2) after retries. "
            f"Mode readback: {mode}, main status: {ms}. Trigger outputs are disabled in Video Mode."
        )

    # Mode transition + park/unpark can reset DP receiver. Re-lock before arming sequencer.
    logger.info("[+] Waiting for external source lock in Video Pattern Mode...")
    if not wait_for_external_lock(dlpc, timeout_s=6.0):
        logger.warning(
            "External lock not re-acquired in mode 2. Proceeding — triggers may be unreliable.")
    else:
        logger.info(
            "[+] External lock confirmed in mode 2. Verifying stable DP input (up to 2s)..."
        )
        if wait_for_stable_external_lock(
            dlpc,
            timeout_s=2.0,
            stable_for_s=0.25,
            required_mode=2,
        ):
            logger.info("[+] Video Pattern Mode input is stable.")
        else:
            logger.warning(
                "Video Pattern Mode input did not remain continuously stable during the 2s "
                "pipeline timeout; continuing after the bounded fallback."
            )

    # DLPU018J Table 2-118/2-120: byte 0 bit 0 = polarity. No enable bit.
    # Non-inverted constraint: rising_delay <= falling_delay. Min pulse width: 20us.
    dlpc.configure_trigger_out_1(polarity_high=True, rising_delay_us=0, falling_delay_us=20)
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_1 config sent. Last error: {err}")

    entries, _, timing = build_lut_entries()
    trigger_out_2_timing = compute_trigger_out_2_timing()
    dlpc.configure_trigger_out_2(
        polarity_high=True,
        rising_delay_us=trigger_out_2_timing["rising_delay_us"],
        falling_delay_us=trigger_out_2_timing["falling_delay_us"],
    )
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_2 config sent. Last error: {err}")
    timing["trigger_out_2"] = trigger_out_2_timing

    t1 = dlpc.get_trigger_out_1()
    t2 = dlpc.get_trigger_out_2()
    logger.info(f"  - TRIG_OUT_1 readback: {t1}")
    logger.info(f"  - TRIG_OUT_2 readback: {t2}")
    logger.info(
        f"[TIMING] LUT timing source: {timing['timing_source']} (effective VSYNC {timing['effective_frame_hz']:.3f} Hz)."
    )
    if timing["measured_frame_hz"] and abs(timing["measured_frame_hz"] - target_hz) > 0.5:
        logger.warning(
            f"Source VSYNC is {timing['measured_frame_hz']:.3f} Hz while fixed target is {target_hz} Hz. "
            f"Sequencer timing follows source VSYNC ({timing['effective_frame_hz']:.3f} Hz).")
    logger.info(
        f"[+] LUT: {timing['entries_count']} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/{timing['usable_frame_period_us']:.1f}us "
        f"(utilization {timing['sequence_utilization']:.2f}, reserved margin {timing['safe_margin_us']:.1f}us, "
        f"idle headroom {timing['idle_headroom_us']:.1f}us from {timing['frame_period_us']:.1f}us VSYNC), "
        f"binary rate req={timing['requested_binary_rate_hz']:.1f}Hz, "
        f"effective={timing['effective_binary_rate_hz']:.1f}Hz")
    logger.info(
        f"[SCOPE] Expected TRIG_OUT_2: rising delay={trigger_out_2_timing['rising_delay_us']}us, "
        f"falling={trigger_out_2_timing['falling_delay_us']}us, active at each bitplane start.")
    logger.info(
        f"[SCOPE] TRIG_OUT_2 mode: per_bitplane (~{timing['effective_binary_rate_hz']:.1f} pulses/s)."
    )
    logger.info(
        f"[SCOPE] Expected TRIG_OUT_1: ~{timing['effective_frame_hz']:.3f} pulses/s. "
        "With dark=0us, pulse may appear as a wide frame-level gate.")

    # Empirically: arming before DLPC900 processes several VSYNCs in mode 2 -> forced-swap (hw 0x08) -> abort (0x40).
    logger.debug("  - Verifying final stable VSYNC input (up to 1s)...")
    if not wait_for_stable_external_lock(
        dlpc,
        timeout_s=1.0,
        stable_for_s=max(0.2, 8.0 / target_hz),
        required_mode=2,
    ):
        logger.warning(
            "Final VSYNC input did not remain continuously stable during the 1s settling "
            "timeout; continuing after the bounded fallback."
        )

    return PreparedSequenceState(entries=entries, timing=timing)

def prepare_pair_controllers(
    dlpc_a: DLPC900,
    dlpc_b: DLPC900,
    *,
    entries_count_a: int,
    entries_count_b: int,) -> None:
    """Prepare both DLPC900 controllers concurrently without starting sequencers."""
    def prepare(label: str, dlpc: DLPC900, entries_count: int) -> None:
        logger.info("[DMD %s] Preparing controller without starting sequencer...", label)
        prepare_dlpc900_for_video_pattern(dlpc, entries_count=entries_count)
        logger.info("[DMD %s] Controller preparation complete.", label)

    # double thread setup for faster setup, from old code
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="dlpc900-prepare") as executor:
        futures = (
            executor.submit(prepare, "A", dlpc_a, entries_count_a),
            executor.submit(prepare, "B", dlpc_b, entries_count_b),
        )
        for future in futures:
            future.result()
            
def configure_dlpc900_for_video_pattern(
    dlpc: DLPC900,
    pre_arm_callback: Callable[[], None] | None = None,
    frame_pump: Callable[[], None] | None = None,
    entries_count: int | None = None,) -> PreparedSequenceState:
    sequence_state = prepare_dlpc900_for_video_pattern(
        dlpc,
        entries_count=entries_count,
    )

    # GL must be rendering when start_pattern_display(2) fires — stale DP frame -> forced-swap.
    if pre_arm_callback is not None:
        pre_arm_callback()

    entries = sequence_state.entries
    logger.info(f"[+] Applying pattern LUT with {len(entries)} entries...")
    apply_pattern_sequence(dlpc, entries, frame_pump=frame_pump)

    logger.info("[+] Pattern sequencer start command issued.")
    verify_started_pattern_sequence(dlpc)
    return sequence_state


def apply_pattern_sequence(
    dlpc: DLPC900,
    entries: Sequence[LutEntry],
    frame_pump: Callable[[], None] | None = None,) -> None:
    load_pattern_sequence(dlpc, entries)

    if frame_pump is not None:
        frame_pump()
    start_loaded_pattern_sequence(dlpc)

    # hw bit 6 (DLPU018J "ABORT") is set by Pattern Display Stop and can persist
    # after a healthy restart. Only retry when bit 6 is paired with real unhealthy
    # state: forced_swap, SEQ_ERR, mode drop, stopped sequencer, or lost sync.
    _RETRY_DELAYS = [0.37, 0.73, 1.17, 1.83, 2.53]
    for attempt in range(1, len(_RETRY_DELAYS) + 1):
        hw = dlpc.get_hardware_status()
        if hw is None or not (hw & 0x40):
            if attempt > 1:
                logger.debug(f"  [arm] bit-6 cleared on attempt {attempt} (hw={_format_hw(hw)}).")
            break

        if _bit6_is_cosmetic(dlpc, hw):
            logger.debug(
                f"  [arm] bit-6 latched but health checks are good "
                f"(hw={_format_hw(hw)}); skipping retry churn.")
            break

        err_code = dlpc.get_last_error()
        err_desc = dlpc.get_error_description()
        logger.debug(
            f"  [arm] bit-6 latched hw={_format_hw(hw)} after start attempt {attempt}. "
            f"last_err={err_code!r} desc={err_desc!r}. "
            f"Stop -> park/unpark -> {_RETRY_DELAYS[attempt - 1]:.2f}s -> resend LUT -> restart.")
        dlpc.start_pattern_display(0)
        time.sleep(0.1)
        hw_after_stop = dlpc.get_hardware_status()
        logger.debug(f"  [retry {attempt}] hw post-stop    = {_format_hw(hw_after_stop)}")
        dlpc.apply_block_lock_workaround()
        hw_after_pp = dlpc.get_hardware_status()
        logger.debug(f"  [retry {attempt}] hw post-park    = {_format_hw(hw_after_pp)}")
        time.sleep(_RETRY_DELAYS[attempt - 1])
        dlpc.set_pattern_lut_definition(entries)
        dlpc.set_pattern_lut_config(len(entries), repeat=True)
        if frame_pump is not None:
            frame_pump()
        dlpc.start_pattern_display(2)
        time.sleep(0.2)
        hw_after_start = dlpc.get_hardware_status()
        logger.debug(f"  [retry {attempt}] hw post-restart = {_format_hw(hw_after_start)}")
    else:
        hw_final = dlpc.get_hardware_status()
        err_code = dlpc.get_last_error()
        err_desc = dlpc.get_error_description()
        logger.warning(
            f"[+] Unhealthy bit-6 state still latched (hw={_format_hw(hw_final)}) "
            f"after {len(_RETRY_DELAYS)} retries. "
            f"last_err={err_code!r} desc={err_desc!r}. "
            "Check sequencer_running, external_source_locked, port1_syncs_valid, forced_swap, and SEQ_ERR."
        )
