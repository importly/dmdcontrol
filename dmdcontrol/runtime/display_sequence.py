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

from argparse import Namespace
from collections.abc import Iterable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Literal, TypedDict

import numpy as np

from dmdcontrol.preview.render import build_lut_preview_metadata

from dmdcontrol.patterns.calibration_square import (
    build_calibration_square_frame,
    make_calibration_square_frame_provider,
)
from dmdcontrol.patterns.kernel import (
    build_kernel_frames,
    compute_kernel_lut_override,
)
from dmdcontrol.patterns.modes import default_calibration_square_state
from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    STATIC_IMAGES_PAIR_TEST,
    STATIC_PAIR_TESTS,
    CalibrationSquareDotPairFrameProvider,
    FramePair,
    PairFrameProvider,
    RGBFrame,
    HalfFramePackingAdapter,
    as_frame_pair,
    generate_dot_frame,
    generate_static_frame,
    make_pair_frame_provider,
    pack_count_sequence_frames,
)
from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.lifecycle import (
    LutEntry,
    LutTimingMetadata,
    build_lut_entries,
)
from dmdcontrol.support.constants import DEFAULT_HZ, DMD_HEIGHT, DMD_WIDTH

ArgsNamespace = Namespace | SimpleNamespace


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

    def lut_plan_for_b(self) -> DmdLutPlan:
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

    def preview_metadata(self) -> dict[str, object]:
        metadata = dict(self.mode_metadata)
        metadata["display_sequence"] = self.metadata()
        plan_a = self.lut_plan_a()
        plan_b = self.lut_plan_for_b()
        preview_a = build_lut_preview_metadata(plan_a.entries, plan_a.timing)
        preview_b = build_lut_preview_metadata(plan_b.entries, plan_b.timing)
        metadata["lut"] = preview_a
        metadata["lut_by_dmd"] = {
            "A": {"role": plan_a.role, "lut": preview_a},
            "B": {"role": plan_b.role, "lut": preview_b},
        }
        metadata["lut_applies_to"] = ["A", "B"] if self.b_lut_plan is None else ["A"]
        return metadata

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


def build_paired_display_sequence(
    args: ArgsNamespace,
    *,
    target_hz: float = DEFAULT_HZ,
    engine: object | None = None,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    if getattr(args, "exposure_us", None) is None:
        raise ValueError("--exposure-us is required for paired LUT workflows")
    if args.test == A_COUNT_B_STATIC_PAIR_TEST:
        return build_count_static_sequence(
            args,
            target_hz=target_hz,
            width=width,
            height=height,
        )
    if args.test == KERNEL_STATIC_PAIR_TEST:
        return build_kernel_static_sequence(
            args,
            target_hz=target_hz,
            engine=engine,
            width=width,
            height=height,
        )
    if args.test == CALIBRATION_DOT_PAIR_TEST:
        return build_calibration_dot_sequence(
            args,
            target_hz=target_hz,
            engine=engine,
            width=width,
            height=height,
        )
    if (
        args.test in STATIC_PAIR_TESTS
        or args.test == STATIC_IMAGES_PAIR_TEST
        or args.test == "snake"
    ):
        return build_provider_backed_sequence(
            args,
            target_hz=target_hz,
            width=width,
            height=height,
        )
    raise ValueError(f"Unsupported paired display sequence mode: {args.test}")


def build_count_static_sequence(
    args: ArgsNamespace,
    *,
    target_hz: float,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    count_config = CountSequenceConfig.from_args(args)
    entries, timing = build_lut_entries(
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=count_config.lut_entries_per_frame,
        per_entry_exposure_us=args.exposure_us,
        dark_time_us=args.dark_time_us,
    )
    base_slots = _slots_from_lut_entries(entries, semantic_role="count")
    # Count mode owns its frame packing here so LUT slots and RGB bitplanes are built together.
    frames_a = pack_count_sequence_frames(
        args.count_start,
        args.count_end,
        args.count_slots_per_frame,
        width=width,
        height=height,
        size_px=args.numbers_size_px,
        count_blank_between_frames=args.count_blank_between_frames,
    )
    frame_b = generate_static_frame(
        args.test_b or "dot",
        width=width,
        height=height,
        route_label="B",
        dot_x=args.b_dot_x,
        dot_y=args.b_dot_y,
        dot_radius=args.b_dot_radius,
        dot_shape=args.b_dot_shape,
        dot_invert=args.b_dot_invert,
    )
    entries_b, timing_b = build_lut_entries(
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=True,
        entries_count=1,
        # Match A's already-resolved exposure instead of filling B to the
        # nominal VSYNC budget. The latter is fragile when the controller's
        # measured VSYNC is a fraction faster than the requested refresh rate.
        # B still remains continuously visible because clear_after is false.
        per_entry_exposure_us=timing["exposure_us"],
        dark_time_us=0,
        clear_last_after_exposure=False,
    )
    frames: list[TimedFramePair] = []
    counts = tuple(range(args.count_start, args.count_end + 1))
    if args.count_blank_between_frames:
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
            zip(frames_a, range(0, len(counts), args.count_slots_per_frame))
        ):
            labels = _count_slot_labels(
                counts[offset : offset + args.count_slots_per_frame],
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
        args.paired_startup_leader_vsyncs,
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
                "exposure_us": args.exposure_us,
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


def build_provider_backed_sequence(
    args: ArgsNamespace,
    *,
    target_hz: float,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    entries, timing = build_lut_entries(
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=None,
        per_entry_exposure_us=args.exposure_us,
        dark_time_us=args.dark_time_us,
    )
    provider = _make_basic_provider(args, width=width, height=height)
    slots = _slots_from_lut_entries(entries, semantic_role=args.test)
    frames = (
        TimedFramePair(
            frame_pair=as_frame_pair(provider.initial_pair()),
            lut_slots=slots,
            source_frame_index=0,
            semantic_labels=(args.test,),
        ),
    )
    return PairedDisplaySequence(
        frames=frames,
        startup_policy=StartupPolicy("blank_leader", args.paired_startup_leader_vsyncs),
        repeat=True,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={},
        provider=provider,
    )


def build_kernel_static_sequence(
    args: ArgsNamespace,
    *,
    target_hz: float,
    engine: object | None = None,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    entries_count, exposure_us = compute_kernel_lut_override(
        enabled=True,
        exposure_us=args.exposure_us,
        target_hz=target_hz,
        sequence_utilization=args.seq_utilization,
        dark_time_us=args.dark_time_us,
    )
    entries, timing = build_lut_entries(
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=exposure_us,
        dark_time_us=args.dark_time_us,
    )
    slots = _slots_from_lut_entries(entries, semantic_role="kernel")
    single_a = HalfFramePackingAdapter(
        width=width,
        height=height,
        window=getattr(engine, "window", None),
    )
    kernel_frames, metadata = build_kernel_frames(
        single_a,
        kernel_px=args.kernel_px,
        slots_per_frame=len(slots),
        leader_frames=args.kernel_leader_frames,
        blank_end_frame=args.kernel_blank_end_frame,
    )
    frame_b = generate_static_frame(
        args.test_b or "checkerboard",
        width=width,
        height=height,
        route_label="B",
        dot_x=args.b_dot_x,
        dot_y=args.b_dot_y,
        dot_radius=args.b_dot_radius,
        dot_shape=args.b_dot_shape,
        dot_invert=args.b_dot_invert,
    )
    frames = tuple(
        TimedFramePair(
            frame_pair=FramePair(a=frame_a, b=frame_b),
            lut_slots=slots,
            source_frame_index=index,
            semantic_labels=(f"kernel-frame:{index}",),
        )
        for index, frame_a in enumerate(kernel_frames)
    )
    terminal_pair = (
        FramePair(a=metadata["black_frame"], b=frame_b)
        if args.kernel_single_shot
        else None
    )
    return PairedDisplaySequence(
        frames=frames,
        startup_policy=StartupPolicy("blank_leader", args.paired_startup_leader_vsyncs),
        repeat=not args.kernel_single_shot,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={
            "kernel": {
                **{
                    key: value
                    for key, value in metadata.items()
                    if key != "black_frame"
                },
                "kernel_px": args.kernel_px,
                "single_shot": args.kernel_single_shot,
                "blank_end_frame": args.kernel_blank_end_frame,
            }
        },
        provider=FrameSequenceProvider(
            frames,
            repeat=not args.kernel_single_shot,
            terminal_pair=terminal_pair,
        ),
    )


def build_calibration_dot_sequence(
    args: ArgsNamespace,
    *,
    target_hz: float,
    engine: object | None = None,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    entries, timing = build_lut_entries(
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=None,
        per_entry_exposure_us=args.exposure_us,
        dark_time_us=args.dark_time_us,
    )
    slots = _slots_from_lut_entries(entries, semantic_role="calibration")
    single_a = HalfFramePackingAdapter(
        width=width,
        height=height,
        window=getattr(engine, "window", None),
    )
    initial_state = default_calibration_square_state(width, height)
    initial_frame = build_calibration_square_frame(single_a, initial_state)
    try:
        frame_provider_a = make_calibration_square_frame_provider(
            single_a,
            initial_frame,
            control_file=args.a_calibr_square_control_file,
            initial_state=initial_state,
        )
    except ModuleNotFoundError as exc:
        if exc.name != "glfw":
            raise
        frame_provider_a = _StaticFrameProvider(initial_frame)
    frame_b = generate_dot_frame(
        width=width,
        height=height,
        x=args.b_dot_x,
        y=args.b_dot_y,
        radius=args.b_dot_radius,
        shape=args.b_dot_shape,
        invert=args.b_dot_invert,
    )
    provider = CalibrationSquareDotPairFrameProvider(
        frame_provider_a,
        frame_b,
        initial_frame_a=initial_frame,
        flicker_a=True,
    )
    return PairedDisplaySequence(
        frames=(
            TimedFramePair(
                frame_pair=as_frame_pair(provider.initial_pair()),
                lut_slots=slots,
                source_frame_index=0,
                semantic_labels=("calibration",),
            ),
        ),
        startup_policy=StartupPolicy("blank_leader", args.paired_startup_leader_vsyncs),
        repeat=True,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={
            "calibration": {"control_file": args.a_calibr_square_control_file}
        },
        provider=provider,
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


def _make_basic_provider(
    args: ArgsNamespace, *, width: int, height: int
) -> PairFrameProvider:
    if args.test in STATIC_PAIR_TESTS:
        return make_pair_frame_provider(
            args.test,
            test_a=args.test_a,
            test_b=args.test_b,
            width=width,
            height=height,
            dot_radius=args.dot_radius,
        )
    if args.test == STATIC_IMAGES_PAIR_TEST:
        return make_pair_frame_provider(
            args.test,
            static_image_a=args.static_image_a,
            static_image_b=args.static_image_b,
            static_image_size_px=args.static_image_size_px,
            width=width,
            height=height,
        )
    return make_pair_frame_provider(args.test, width=width, height=height)


class _StaticFrameProvider:
    def __init__(self, frame: RGBFrame) -> None:
        self._frame = frame

    def __call__(self) -> RGBFrame:
        return self._frame
