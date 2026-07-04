"""Common paired display sequence model.

The paired pipeline intentionally has one ownership point for timing now:

1. Pattern adapters build ordinary RGB `FramePair` images.
2. Each RGB image packs one or more semantic masks into selected bitplanes.
3. Each `LutSlot` points at one packed bitplane and defines exposure, dark time,
   trigger enablement, and a human-readable semantic label.
4. The paired runtime loads `sequence.lut_entries()` into both DLPC900 boards
   and renders `sequence.provider`, so displayed frames and LUT timing cannot
   drift into separate interpretations.

For count/blank mode, one source RGB frame contains `count:N` in bitplane 0 and
`blank` in bitplane 1. The two corresponding LUT slots fire in order at equal
duration, giving `1, blank, 2, blank, ...` without a runtime handoff guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from dmdcontrol.patterns.calibration_square import (
    build_calibration_square_frame,
    make_calibration_square_frame_provider,
)
from dmdcontrol.patterns.kernel import (
    KernelFrameProvider,
    build_kernel_frames,
    compute_kernel_lut_override,
)
from dmdcontrol.patterns.modes import default_calibration_square_state
from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    CalibrationSquareDotPairFrameProvider,
    FramePair,
    STATIC_IMAGES_PAIR_TEST,
    STATIC_PAIR_TESTS,
    DynamicAStaticBPairFrameProvider,
    SingleDmdFrameAdapter,
    as_frame_pair,
    generate_dot_frame,
    generate_static_frame,
    make_pair_frame_provider,
)
from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.lifecycle import build_lut_entries
from dmdcontrol.support.constants import DEFAULT_HZ, DMD_HEIGHT, DMD_WIDTH


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

    def to_lut_entry(self):
        return (
            int(self.bitplane_index),
            int(self.exposure_us),
            bool(self.clear_after),
            1,
            7,
            int(self.dark_us),
            not bool(self.trig2_enabled),
            int(self.bitplane_index),
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


@dataclass(frozen=True)
class PairedDisplaySequence:
    """Complete frame/timing contract consumed by paired runtime and metadata."""

    frames: tuple[TimedFramePair, ...]
    startup_policy: StartupPolicy
    repeat: bool
    target_hz: float
    timing: dict[str, object]
    mode_metadata: dict[str, object] = field(default_factory=dict)
    provider: object | None = None

    def __post_init__(self):
        if not self.frames:
            raise ValueError("PairedDisplaySequence requires at least one frame")
        slot_count = len(self.frames[0].lut_slots)
        if slot_count <= 0:
            raise ValueError("PairedDisplaySequence frames require at least one LUT slot")
        for frame in self.frames:
            if len(frame.lut_slots) != slot_count:
                raise ValueError("all source frames must use the same LUT slot count")

    @property
    def lut_slots(self) -> tuple[LutSlot, ...]:
        return self.frames[0].lut_slots

    def lut_entries(self):
        return [slot.to_lut_entry() for slot in self.lut_slots]

    def startup_leader_metadata(self) -> dict[str, object]:
        entries_count = len(self.lut_slots)
        leader_vsyncs = int(self.startup_policy.leader_vsyncs)
        trigger_count = 0
        if self.startup_policy.mode == "blank_leader":
            trigger_count = leader_vsyncs if self.timing.get("trig2_mode") == "frame_zero" else (
                leader_vsyncs * entries_count)
        return {
            "vsyncs": leader_vsyncs,
            "trigger_count": int(trigger_count),
            "entries_count": entries_count,
            "trig2_mode": self.timing.get("trig2_mode") or "per_bitplane",
            "frame_role": "blank_startup_leader",
            "startup_policy": self.startup_policy.mode,
        }

    def metadata(self) -> dict[str, object]:
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
                        } for slot in frame.lut_slots
                    ],
                } for frame in self.frames
            ],
        }

    def preview_metadata(self) -> dict[str, object]:
        from dmdcontrol.preview.render import build_lut_preview_metadata

        metadata = dict(self.mode_metadata)
        metadata["display_sequence"] = self.metadata()
        metadata["lut"] = build_lut_preview_metadata(self.lut_entries(), self.timing)
        metadata["lut_applies_to"] = ["A", "B"]
        return metadata

    def expected_trigger_count(self) -> int:
        return sum(1 for frame in self.frames for slot in frame.lut_slots if slot.trig2_enabled)

    def first_frame_pair(self) -> FramePair:
        return self.frames[0].frame_pair


class _DryRunDLPC:

    def get_display_dimensions(self):
        return None


def build_paired_display_sequence(
    args,
    *,
    target_hz: float = DEFAULT_HZ,
    engine=None,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
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
    if args.test in STATIC_PAIR_TESTS or args.test == STATIC_IMAGES_PAIR_TEST or args.test == "snake":
        return build_provider_backed_sequence(
            args,
            target_hz=target_hz,
            width=width,
            height=height,
        )
    raise ValueError(f"Unsupported paired display sequence mode: {args.test}")


def build_count_static_sequence(
    args,
    *,
    target_hz: float,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    count_config = CountSequenceConfig.from_args(args)
    entries, timing = build_lut_entries(
        _DryRunDLPC(),
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=count_config.lut_entries_per_frame,
        per_entry_exposure_us=args.exposure_us,
        dark_time_us=args.dark_time_us,
    )
    base_slots = _slots_from_lut_entries(entries, semantic_role="count")
    provider = make_pair_frame_provider(
        args.test,
        test_b=args.test_b,
        count_start=args.count_start,
        count_end=args.count_end,
        count_slots_per_frame=args.count_slots_per_frame,
        count_blank_between_frames=args.count_blank_between_frames,
        numbers_size_px=args.numbers_size_px,
        b_dot_x=args.b_dot_x,
        b_dot_y=args.b_dot_y,
        b_dot_radius=args.b_dot_radius,
        b_dot_shape=args.b_dot_shape,
        b_dot_invert=args.b_dot_invert,
        width=width,
        height=height,
    )
    frames = []
    counts = tuple(range(args.count_start, args.count_end + 1))
    for source_frame_index, offset in enumerate(range(0, len(counts), args.count_slots_per_frame)):
        frame_pair = provider.initial_pair() if source_frame_index == 0 else provider.next_pair()
        labels = _count_slot_labels(
            counts[offset:offset + args.count_slots_per_frame],
            blank_after_each_count=args.count_blank_between_frames,
        )
        frames.append(
            TimedFramePair(
                frame_pair=as_frame_pair(frame_pair),
                lut_slots=_slots_with_labels(base_slots, labels),
                source_frame_index=source_frame_index,
                semantic_labels=tuple(label for label in labels if label != "blank"),
            ))
    startup_policy = (
        StartupPolicy("prime_first_frame", 0)
        if args.count_blank_between_frames else
        StartupPolicy("blank_leader", args.paired_startup_leader_vsyncs)
    )
    return PairedDisplaySequence(
        frames=tuple(frames),
        startup_policy=startup_policy,
        repeat=True,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={
            "count": {
                **count_config.to_pair_preview_metadata(),
                "exposure_us": args.exposure_us,
            }
        },
        provider=provider,
    )


def build_provider_backed_sequence(
    args,
    *,
    target_hz: float,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    entries, timing = build_lut_entries(
        _DryRunDLPC(),
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=None,
        per_entry_exposure_us=args.exposure_us,
        dark_time_us=args.dark_time_us,
    )
    provider = _make_basic_provider(args, width=width, height=height)
    slots = _slots_from_lut_entries(entries, semantic_role=args.test)
    return PairedDisplaySequence(
        frames=(
            TimedFramePair(
                frame_pair=as_frame_pair(provider.initial_pair()),
                lut_slots=slots,
                source_frame_index=0,
                semantic_labels=(args.test,),
            ),
        ),
        startup_policy=StartupPolicy("blank_leader", args.paired_startup_leader_vsyncs),
        repeat=True,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={},
        provider=provider,
    )


def build_kernel_static_sequence(
    args,
    *,
    target_hz: float,
    engine=None,
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
        _DryRunDLPC(),
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=exposure_us,
        dark_time_us=args.dark_time_us,
    )
    slots = _slots_from_lut_entries(entries, semantic_role="kernel")
    single_a = SingleDmdFrameAdapter(
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
        ) for index, frame_a in enumerate(kernel_frames)
    )
    frame_provider_a = KernelFrameProvider(
        kernel_frames,
        black_frame=metadata["black_frame"],
        single_shot=args.kernel_single_shot,
    )
    provider = DynamicAStaticBPairFrameProvider(
        frame_provider_a,
        frame_b,
        initial_frame_a=kernel_frames[0],
    )
    return PairedDisplaySequence(
        frames=frames,
        startup_policy=StartupPolicy("blank_leader", args.paired_startup_leader_vsyncs),
        repeat=not args.kernel_single_shot,
        target_hz=target_hz,
        timing=timing,
        mode_metadata={
            "kernel": {
                **{key: value for key, value in metadata.items() if key != "black_frame"},
                "kernel_px": args.kernel_px,
                "single_shot": args.kernel_single_shot,
                "blank_end_frame": args.kernel_blank_end_frame,
            }
        },
        provider=provider,
    )


def build_calibration_dot_sequence(
    args,
    *,
    target_hz: float,
    engine=None,
    width: int = DMD_WIDTH,
    height: int = DMD_HEIGHT,
) -> PairedDisplaySequence:
    entries, timing = build_lut_entries(
        _DryRunDLPC(),
        target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=None,
        per_entry_exposure_us=args.exposure_us,
        dark_time_us=args.dark_time_us,
    )
    slots = _slots_from_lut_entries(entries, semantic_role="calibration")
    single_a = SingleDmdFrameAdapter(
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
        mode_metadata={"calibration": {"control_file": args.a_calibr_square_control_file}},
        provider=provider,
    )


def _slots_from_lut_entries(entries, *, semantic_role: str) -> tuple[LutSlot, ...]:
    slots = []
    for entry in entries:
        bitplane_index, exposure_us, clear_after, _depth, _led, dark_us, trig2_disabled, _bit_pos = entry
        slots.append(
            LutSlot(
                bitplane_index=int(bitplane_index),
                exposure_us=int(exposure_us),
                dark_us=int(dark_us),
                trig2_enabled=not bool(trig2_disabled),
                clear_after=bool(clear_after),
                semantic_role=semantic_role,
            ))
    return tuple(slots)


def _slots_with_labels(slots: tuple[LutSlot, ...], labels: list[str]) -> tuple[LutSlot, ...]:
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
            ))
    return tuple(labeled)


def _count_slot_labels(counts, *, blank_after_each_count: bool) -> list[str]:
    labels = []
    for count in counts:
        labels.append(f"count:{count}")
        if blank_after_each_count:
            labels.append("blank")
    return labels


def _make_basic_provider(args, *, width: int, height: int):
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

    def __init__(self, frame):
        self._frame = frame

    def __call__(self):
        return self._frame
