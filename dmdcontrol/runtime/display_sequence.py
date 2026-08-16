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
    entries_b, timing_b, timing_b = build_lut_entries(
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
    entries, timing = build_lut_entries()
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
