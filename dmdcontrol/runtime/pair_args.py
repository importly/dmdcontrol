"""Argument parsing and validation for paired DMD runtime."""

from __future__ import annotations

import argparse

from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    PAIR_TESTS,
    STATIC_IMAGES_PAIR_TEST,
    STATIC_PAIR_TESTS,
)
from dmdcontrol.runtime.count_slots import CountSequenceConfig, resolve_count_slots_per_frame
from dmdcontrol.runtime.lifecycle import compute_trigger_out_2_timing
from dmdcontrol.support.argparse_types import (
    count_slots_per_frame,
    nonnegative_int,
    positive_float,
    positive_int,
    trigger_out_rising_delay_us,
    unit_interval_float,
)
from dmdcontrol.support.constants import (
    DEFAULT_COUNT_END,
    DEFAULT_COUNT_START,
    DEFAULT_DOT_RADIUS_PX,
    DEFAULT_HZ,
    DEFAULT_KERNEL_LEADER_FRAMES,
    DEFAULT_KERNEL_PX,
    DEFAULT_PAIRED_STARTUP_LEADER_VSYNCS,
    DEFAULT_PREVIEW_FPS,
    DEFAULT_RUNTIME_SECONDS,
    DEFAULT_SEQUENCE_UTILIZATION,
    DEFAULT_TRIGGER_OUT_2_RISING_DELAY_US,
    DMD_CENTER_X,
    DMD_CENTER_Y,
    DMD_HEIGHT,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dual DLPC900 paired Video Pattern Mode runtime")
    parser.add_argument("--dmd-config", default=None, help="Path to DMD mapping config")
    parser.add_argument("--test", choices=PAIR_TESTS, default="checkerboard")
    parser.add_argument(
        "--test-a",
        choices=STATIC_PAIR_TESTS,
        default=None,
        help="Static pattern for DMD A when --test is a static paired mode",
    )
    parser.add_argument(
        "--test-b",
        choices=STATIC_PAIR_TESTS,
        default=None,
        help="Static pattern for DMD B when --test is a static paired mode",
    )
    parser.add_argument("--runtime-seconds", type=nonnegative_int, default=DEFAULT_RUNTIME_SECONDS)
    parser.add_argument(
        "--a-calibr-square-control-file",
        default=None,
        help="Control-file path for DMD A calibration-square edits in paired calibration-dot mode",
    )
    parser.add_argument("--b-dot-x", type=int, default=DMD_CENTER_X)
    parser.add_argument("--b-dot-y", type=int, default=DMD_CENTER_Y)
    parser.add_argument("--b-dot-radius", type=positive_int, default=DEFAULT_DOT_RADIUS_PX)
    parser.add_argument(
        "--dot-radius",
        type=positive_int,
        default=DEFAULT_DOT_RADIUS_PX,
        help="Radius for generic static dot frames, for example --test dot",
    )
    parser.add_argument(
        "--b-dot-shape",
        choices=("circle",
                 "square"),
        default="circle",
    )
    parser.add_argument("--b-dot-invert", action="store_true")
    parser.add_argument(
        "--kernel-px",
        type=positive_int,
        default=DEFAULT_KERNEL_PX,
        help="A-kernel paired recipe: total 3x3 kernel side length in pixels",
    )
    parser.add_argument(
        "--kernel-single-shot",
        action="store_true",
        help="A-kernel paired recipe: play one kernel cycle then hold black on A",
    )
    parser.add_argument(
        "--kernel-blank-end-frame",
        dest="kernel_blank_end_frame",
        action="store_true",
        default=True,
        help="A-kernel paired recipe: append one all-black VSYNC frame to each cycle",
    )
    parser.add_argument(
        "--no-kernel-blank-end-frame",
        dest="kernel_blank_end_frame",
        action="store_false",
        help="A-kernel paired recipe: omit the all-black end marker frame",
    )
    parser.add_argument(
        "--kernel-leader-frames",
        type=nonnegative_int,
        default=DEFAULT_KERNEL_LEADER_FRAMES,
        help="A-kernel paired recipe: all-black VSYNC frames prepended to each cycle",
    )
    parser.add_argument(
        "--numbers-size-px",
        type=positive_int,
        default=None,
        help="A-count paired recipe: seven-segment digit height in pixels",
    )
    parser.add_argument(
        "--count-start",
        type=positive_int,
        default=DEFAULT_COUNT_START,
        help="A-count paired recipe: first integer label to display",
    )
    parser.add_argument(
        "--count-end",
        type=positive_int,
        default=DEFAULT_COUNT_END,
        help="A-count paired recipe: final integer label to display, inclusive",
    )
    parser.add_argument(
        "--count-slots-per-frame",
        type=count_slots_per_frame,
        default=None,
        help=(
            "A-count paired recipe: count labels packed into bitplanes per VSYNC frame "
            "when blank-after mode is off. Use 'auto' or omit to choose the fastest "
            "timing-valid divisor."),
    )
    parser.add_argument(
        "--count-blank-after-each-count",
        dest="count_blank_between_frames",
        action="store_true",
        help="A-count paired recipe: insert an all-black A frame after each displayed count.",
    )
    parser.add_argument(
        "--count-blank-between-frames",
        dest="count_blank_between_frames",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--static-image-a",
        default=None,
        help="Static-images paired recipe: image path displayed on DMD A",
    )
    parser.add_argument(
        "--static-image-b",
        default=None,
        help="Static-images paired recipe: image path displayed on DMD B",
    )
    parser.add_argument(
        "--static-image-size-px",
        type=positive_int,
        default=DMD_HEIGHT,
        help=(
            "Static-images paired recipe: longest image side after aspect-preserving resize; "
            "the result is centered on each DMD."),
    )
    parser.add_argument(
        "--wake-dp",
        action="store_true",
        help="Wake both DP receivers before runtime")
    parser.add_argument(
        "--dual-pixel",
        action="store_true",
        help="Force dual-pixel P1-P2 mode on both DLPC900 controllers",
    )
    parser.add_argument(
        "--seq-utilization",
        type=unit_interval_float,
        default=DEFAULT_SEQUENCE_UTILIZATION,
        help="Fraction of safe frame budget allocated to LUT exposure timing",
    )
    parser.add_argument(
        "--trig2-frame-zero",
        action="store_true",
        help="Emit TRIG_OUT_2 only for bitplane/frame-zero anchor entries",
    )
    parser.add_argument(
        "--paired-startup-leader-vsyncs",
        type=nonnegative_int,
        default=DEFAULT_PAIRED_STARTUP_LEADER_VSYNCS,
        help=(
            "Blank paired source VSYNCs displayed after both sequencers start "
            "before the first semantic frame. These trigger pulses are recorded "
            "in startup_leader metadata and skipped by camera artifact generation."),
    )
    parser.add_argument(
        "--trigger-out-2-rising-delay-us",
        type=trigger_out_rising_delay_us,
        default=DEFAULT_TRIGGER_OUT_2_RISING_DELAY_US,
        help="TRIG_OUT_2 rising-edge delay in microseconds. Valid range: -20 to 19980. Default: 0.",
    )
    parser.add_argument(
        "--exposure-us",
        type=positive_int,
        default=None,
        help="Optional per-DLPC900-LUT-entry exposure override in microseconds",
    )
    parser.add_argument(
        "--dark-time-us",
        type=int,
        default=None,
        help="Optional override for INTER_PATTERN_DARK_US",
    )
    parser.add_argument(
        "--dry-run-timing",
        action="store_true",
        help="Print paired mapping and LUT timing without importing OpenGL or USB hardware",
    )
    parser.add_argument(
        "--preview-url",
        default=None,
        help="Optional live-preview POST endpoint, for example http://127.0.0.1:8080/api/live-frame",
    )
    parser.add_argument(
        "--preview-fps",
        type=positive_float,
        default=DEFAULT_PREVIEW_FPS,
        help="Maximum live-preview POST rate when --preview-url is set",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def _is_count_recipe(test: str) -> bool:
    return test == A_COUNT_B_STATIC_PAIR_TEST


def _resolve_count_recipe_args(args: argparse.Namespace, target_hz: float = DEFAULT_HZ) -> None:
    if not _is_count_recipe(args.test):
        return
    mode = "auto" if args.count_slots_per_frame is None else "explicit"
    if mode == "auto":
        try:
            args.count_slots_per_frame = resolve_count_slots_per_frame(
                count_start=args.count_start,
                count_end=args.count_end,
                exposure_us=args.exposure_us,
                dark_time_us=args.dark_time_us,
                count_blank_between_frames=args.count_blank_between_frames,
                target_hz=target_hz,
                sequence_utilization=args.seq_utilization,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
    args.count_slots_per_frame_mode = mode


def _validate_pair_args(args: argparse.Namespace, target_hz: float = DEFAULT_HZ) -> None:
    if args.preview_fps <= 0:
        raise SystemExit("--preview-fps must be positive")
    try:
        compute_trigger_out_2_timing(rising_delay_us=args.trigger_out_2_rising_delay_us)
    except ValueError as exc:
        raise SystemExit(f"--trigger-out-2-rising-delay-us is invalid: {exc}") from exc
    if args.dark_time_us is not None and args.dark_time_us < 0:
        raise SystemExit("--dark-time-us must be non-negative")
    if not _is_count_recipe(args.test) and args.count_blank_between_frames:
        raise SystemExit("count blank insertion is only valid for a-count-b-static")
    if args.test == STATIC_IMAGES_PAIR_TEST:
        if args.test_a or args.test_b:
            raise SystemExit("--test-a/--test-b are not valid for static-images; use image paths")
        if not args.static_image_a or not args.static_image_b:
            raise SystemExit("static-images requires --static-image-a and --static-image-b")
        return
    if args.test == KERNEL_STATIC_PAIR_TEST:
        if args.test_a:
            raise SystemExit("--test-a is not valid for a-kernel-b-static; A is the kernel stream")
        return
    if _is_count_recipe(args.test):
        _resolve_count_recipe_args(args, target_hz=target_hz)
        _validate_count_recipe_args(args, target_hz=target_hz)
        return
    if args.test not in STATIC_PAIR_TESTS and (args.test_a or args.test_b):
        raise SystemExit("--test-a/--test-b are only valid for static paired tests")


def _validate_count_recipe_args(args: argparse.Namespace, target_hz: float = DEFAULT_HZ) -> None:
    if args.test_a:
        raise SystemExit("--test-a is not valid for a-count-b-static; A is the count stream")
    try:
        config = CountSequenceConfig.from_args(args)
        config.validate_shape()
        config.validate_timing(
            exposure_us=args.exposure_us,
            dark_time_us=args.dark_time_us,
            target_hz=target_hz,
            sequence_utilization=args.seq_utilization,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
