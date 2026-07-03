from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.lifecycle import compute_trigger_out_2_timing

A_COUNT_B_STATIC_TEST = "a-count-b-static"


def expected_trigger_count(args: argparse.Namespace) -> int:
    if args.test == A_COUNT_B_STATIC_TEST:
        config = CountSequenceConfig.from_args(args)
        return config.expected_trigger_count
    return len(args.numbers)


def _pair_runtime_seconds(args: argparse.Namespace) -> int:
    runtime_seconds = args.runtime_seconds
    if runtime_seconds <= 0:
        if args.exposure_us is None:
            runtime_seconds = 1
        else:
            per_slot_us = args.exposure_us + max(0, args.dark_time_us or 0)
            sequence_seconds = expected_trigger_count(args) * per_slot_us / 1_000_000.0
            runtime_seconds = max(1, math.ceil(sequence_seconds))
    return runtime_seconds


def _requested_accumulation_window_us(args: argparse.Namespace) -> int | None:
    return args.exposure_us


def _trigger_policy(args: argparse.Namespace) -> dict[str, object]:
    timing = compute_trigger_out_2_timing(
        rising_delay_us=args.trigger_out_2_rising_delay_us)
    return {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": timing["rising_delay_us"],
        "falling_delay_us": timing["falling_delay_us"],
    }


@dataclass(frozen=True)
class PairRuntimeRequest:
    """Sync-check display request translated into pair-runtime terms.

    `to_namespace()` is for in-process execution and preserves semantic choices
    like auto-resolved count slots. `to_argv()` is only for readable command
    artifacts and compatibility tests.
    """

    test: str
    test_b: str
    b_dot_x: int
    b_dot_y: int
    b_dot_radius: int
    runtime_seconds: int
    paired_startup_leader_vsyncs: int
    trigger_out_2_rising_delay_us: int
    number_size_px: int | None = None
    kernel_px: int | None = None
    numbers: tuple[int, ...] = ()
    numbers_bitplane_order: tuple[int, ...] | None = None
    count_start: int | None = None
    count_end: int | None = None
    count_slots_per_frame: int | None = None
    count_slots_per_frame_mode: str = "explicit"
    count_blank_between_frames: bool = False
    exposure_us: int | None = None
    seq_utilization: float | None = None
    dark_time_us: int | None = None
    dmd_config: str | None = None
    verbose: int = 0

    @classmethod
    def from_sync_args(cls, args: argparse.Namespace) -> "PairRuntimeRequest":
        return cls(
            test=args.test,
            test_b=args.test_b,
            b_dot_x=args.b_dot_x,
            b_dot_y=args.b_dot_y,
            b_dot_radius=args.b_dot_radius,
            runtime_seconds=_pair_runtime_seconds(args),
            paired_startup_leader_vsyncs=args.paired_startup_leader_vsyncs,
            trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
            number_size_px=args.number_size_px,
            numbers=tuple(getattr(args, "numbers", ())),
            numbers_bitplane_order=(
                tuple(args.numbers_bitplane_order)
                if args.numbers_bitplane_order is not None else None
            ),
            count_start=getattr(args, "count_start", None),
            count_end=getattr(args, "count_end", None),
            count_slots_per_frame=getattr(args, "count_slots_per_frame", None),
            count_slots_per_frame_mode=getattr(args, "count_slots_per_frame_mode", "explicit"),
            count_blank_between_frames=getattr(args, "count_blank_between_frames", False),
            exposure_us=args.exposure_us,
            seq_utilization=args.seq_utilization,
            dark_time_us=getattr(args, "dark_time_us", None),
            dmd_config=args.dmd_config,
            verbose=args.verbose or 0,
        )

    @classmethod
    def from_pair_capture_args(cls, args: argparse.Namespace) -> "PairRuntimeRequest":
        return cls(
            test=args.test,
            test_b=args.test_b,
            b_dot_x=args.b_dot_x,
            b_dot_y=args.b_dot_y,
            b_dot_radius=args.b_dot_radius,
            runtime_seconds=args.runtime_seconds,
            paired_startup_leader_vsyncs=args.paired_startup_leader_vsyncs,
            trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
            kernel_px=args.kernel_px,
            exposure_us=args.exposure_us,
            dark_time_us=getattr(args, "dark_time_us", None),
            dmd_config=args.dmd_config,
            verbose=args.verbose or 0,
        )

    def to_namespace(self, *, dry_run_timing: bool = False) -> argparse.Namespace:
        from dmdcontrol.runtime import pair as pair_module

        namespace = pair_module._build_parser().parse_args([])
        overrides = {
            "dry_run_timing": dry_run_timing,
            "test": self.test,
            "test_b": self.test_b,
            "b_dot_x": self.b_dot_x,
            "b_dot_y": self.b_dot_y,
            "b_dot_radius": self.b_dot_radius,
            "runtime_seconds": self.runtime_seconds,
            "paired_startup_leader_vsyncs": self.paired_startup_leader_vsyncs,
            "trigger_out_2_rising_delay_us": self.trigger_out_2_rising_delay_us,
            "numbers_size_px": self.number_size_px,
            "kernel_px": self.kernel_px,
            "exposure_us": self.exposure_us,
            "dark_time_us": self.dark_time_us,
            "dmd_config": self.dmd_config,
            "verbose": self.verbose,
        }
        if self.seq_utilization is not None:
            overrides["seq_utilization"] = self.seq_utilization
        if self.test == A_COUNT_B_STATIC_TEST:
            overrides.update({
                "count_start": self.count_start,
                "count_end": self.count_end,
                "count_slots_per_frame": (
                    None if self.count_slots_per_frame_mode == "auto"
                    else self.count_slots_per_frame
                ),
                "count_slots_per_frame_mode": self.count_slots_per_frame_mode,
                "count_blank_between_frames": self.count_blank_between_frames,
            })
        elif self.numbers:
            overrides.update({
                "numbers": list(self.numbers),
                "numbers_bitplane_order": (
                    list(self.numbers_bitplane_order)
                    if self.numbers_bitplane_order is not None else None
                ),
            })
        vars(namespace).update(overrides)
        return namespace

    def to_argv(self, *, dry_run_timing: bool = False) -> list[str]:
        pair_args = ["--dry-run-timing"] if dry_run_timing else []
        pair_args.extend(_argv_options((
            ("--test", self.test),
            ("--test-b", self.test_b),
            ("--b-dot-x", self.b_dot_x),
            ("--b-dot-y", self.b_dot_y),
            ("--b-dot-radius", self.b_dot_radius),
            ("--runtime-seconds", self.runtime_seconds),
            ("--paired-startup-leader-vsyncs", self.paired_startup_leader_vsyncs),
            ("--trigger-out-2-rising-delay-us", self.trigger_out_2_rising_delay_us),
            ("--kernel-px", self.kernel_px),
        ), skip_none=True))

        if self.test == A_COUNT_B_STATIC_TEST:
            pair_args.extend(_argv_options((
                ("--count-start", self.count_start),
                ("--count-end", self.count_end),
                ("--numbers-size-px", self.number_size_px),
                ("--count-slots-per-frame", self.count_slots_per_frame),
            ), skip_none=True))
            if self.count_blank_between_frames:
                pair_args.append("--count-blank-after-each-count")
        elif self.numbers:
            pair_args.extend(_argv_options((
                ("--numbers", ",".join(str(number) for number in self.numbers)),
                ("--numbers-size-px", self.number_size_px),
            )))
            if self.numbers_bitplane_order is not None:
                pair_args.extend(_argv_options(((
                    "--numbers-bitplane-order",
                    ",".join(str(index) for index in self.numbers_bitplane_order),
                ),)))
        pair_args.extend(_argv_options((
            ("--exposure-us", self.exposure_us),
            ("--seq-utilization", self.seq_utilization),
            ("--dark-time-us", self.dark_time_us),
            ("--dmd-config", self.dmd_config),
        ), skip_none=True))
        pair_args.extend(["-v"] * self.verbose)
        return pair_args


def pair_runtime_request_from_args(args: argparse.Namespace) -> PairRuntimeRequest:
    return PairRuntimeRequest.from_sync_args(args)


def _argv_options(pairs, *, skip_none: bool = False) -> list[str]:
    return [
        item
        for flag, value in pairs
        if not (skip_none and value is None)
        for item in (flag, str(value))
    ]
