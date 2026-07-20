from __future__ import annotations

import argparse
import math

from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.pair import _build_parser as build_pair_parser
from dmdcontrol.runtime.lifecycle import compute_trigger_out_2_timing

A_COUNT_B_STATIC_TEST = "a-count-b-static"


def expected_trigger_count(args: argparse.Namespace) -> int:
    if args.test == A_COUNT_B_STATIC_TEST:
        config = CountSequenceConfig.from_args(args)
        return config.expected_trigger_count
    raise ValueError(f"Unsupported sync-check test mode: {args.test}")


def _pair_runtime_seconds(args: argparse.Namespace) -> int:
    runtime_seconds = args.runtime_seconds
    if runtime_seconds <= 0:
        per_slot_us = args.exposure_us + max(0, args.dark_time_us or 0)
        sequence_seconds = expected_trigger_count(args) * per_slot_us / 1_000_000.0
        runtime_seconds = max(1, math.ceil(sequence_seconds))
    return runtime_seconds


def trigger_policy(args: argparse.Namespace) -> dict[str, object]:
    timing = compute_trigger_out_2_timing(
        rising_delay_us=args.trigger_out_2_rising_delay_us
    )
    return {
        "channel": "TRIG_OUT_2",
        "source_dmd": "A",
        "edge": "rising",
        "rising_delay_us": timing["rising_delay_us"],
        "falling_delay_us": timing["falling_delay_us"],
    }


_SHARED_PAIR_FIELDS = (
    "test",
    "test_b",
    "b_dot_x",
    "b_dot_y",
    "b_dot_radius",
    "paired_startup_leader_vsyncs",
    "trigger_out_2_rising_delay_us",
    "exposure_us",
    "dark_time_us",
    "dmd_config",
)


def _pair_runtime_args(args: argparse.Namespace) -> argparse.Namespace:
    pair_args = build_pair_parser().parse_args(["--exposure-us", str(args.exposure_us)])
    for name in _SHARED_PAIR_FIELDS:
        setattr(pair_args, name, getattr(args, name))
    pair_args.verbose = args.verbose or 0
    return pair_args


def pair_runtime_args_from_sync(args: argparse.Namespace) -> argparse.Namespace:
    pair_args = _pair_runtime_args(args)
    pair_args.runtime_seconds = _pair_runtime_seconds(args)
    pair_args.numbers_size_px = args.number_size_px
    if args.seq_utilization is not None:
        pair_args.seq_utilization = args.seq_utilization

    if args.test == A_COUNT_B_STATIC_TEST:
        config = CountSequenceConfig.from_args(args)
        pair_args.count_start = config.count_start
        pair_args.count_end = config.count_end
        pair_args.count_slots_per_frame = (
            None
            if config.count_slots_per_frame_mode == "auto"
            else config.count_slots_per_frame
        )
        pair_args.count_slots_per_frame_mode = config.count_slots_per_frame_mode
        pair_args.count_blank_between_frames = config.count_blank_between_frames
    return pair_args


def pair_runtime_args_from_capture(args: argparse.Namespace) -> argparse.Namespace:
    pair_args = _pair_runtime_args(args)
    pair_args.runtime_seconds = args.runtime_seconds
    pair_args.kernel_px = args.kernel_px
    return pair_args
