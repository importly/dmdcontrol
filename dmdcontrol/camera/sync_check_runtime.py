from __future__ import annotations

import argparse
import math

from dmdcontrol.runtime.lifecycle import compute_trigger_out_2_timing

A_COUNT_B_STATIC_TEST = "a-count-b-static"


def expected_trigger_count(args: argparse.Namespace) -> int:
    if args.test == A_COUNT_B_STATIC_TEST:
        return args.count_end - args.count_start + 1
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


def _to_pair_runtime_args(args: argparse.Namespace) -> list[str]:
    runtime_seconds = _pair_runtime_seconds(args)
    pair_args = [
        "--test",
        args.test,
        "--test-b",
        args.test_b,
        "--b-dot-x",
        str(args.b_dot_x),
        "--b-dot-y",
        str(args.b_dot_y),
        "--b-dot-radius",
        str(args.b_dot_radius),
        "--runtime-seconds",
        str(runtime_seconds),
        "--trigger-out-2-rising-delay-us",
        str(args.trigger_out_2_rising_delay_us),
    ]

    if args.test == A_COUNT_B_STATIC_TEST:
        pair_args.extend(
            [
                "--count-start",
                str(args.count_start),
                "--count-end",
                str(args.count_end),
                "--count-slots-per-frame",
                str(args.count_slots_per_frame),
                "--numbers-size-px",
                str(args.number_size_px),
            ])
    else:
        pair_args.extend(
            [
                "--numbers",
                ",".join(str(number) for number in args.numbers),
                "--numbers-size-px",
                str(args.number_size_px),
            ])
        if args.numbers_bitplane_order is not None:
            pair_args.extend(
                [
                    "--numbers-bitplane-order",
                    ",".join(str(index) for index in args.numbers_bitplane_order),
                ])
    if args.exposure_us is not None:
        pair_args.extend(["--exposure-us", str(args.exposure_us)])
    if args.seq_utilization is not None:
        pair_args.extend(["--seq-utilization", str(args.seq_utilization)])
    if getattr(args, "dark_time_us", None) is not None:
        pair_args.extend(["--dark-time-us", str(args.dark_time_us)])
    if args.dmd_config is not None:
        pair_args.extend(["--dmd-config", args.dmd_config])
    for _ in range(args.verbose or 0):
        pair_args.append("-v")
    return pair_args
