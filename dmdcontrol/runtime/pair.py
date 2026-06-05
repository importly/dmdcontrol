"""Paired dual-DMD runtime for one 3840x1080 OpenGL swap loop."""

from __future__ import annotations

import argparse
import math
import threading
import time
from dataclasses import dataclass

from dmdcontrol.hardware.mapping import DmdMapping, resolve_dmd_mapping
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
    A_NUMBERS_B_STATIC_PAIR_TEST,
    CALIBRATION_DOT_PAIR_TEST,
    CalibrationSquareDotPairFrameProvider,
    DynamicAStaticBPairFrameProvider,
    KERNEL_STATIC_PAIR_TEST,
    MAX_COUNT_SEQUENCE_FRAMES,
    NUMBER_PAIR_TEST,
    OFFSET_A,
    OFFSET_B,
    PAIR_HEIGHT,
    PAIR_TESTS,
    PAIR_WIDTH,
    STATIC_PAIR_TESTS,
    SingleDmdFrameAdapter,
    count_sequence_frame_count,
    generate_dot_frame,
    generate_static_frame,
    make_pair_frame_provider,
)
from dmdcontrol.preview.render import LivePreviewPoster, build_lut_preview_metadata
from dmdcontrol.runtime.lifecycle import (
    build_lut_entries,
    compute_trigger_out_2_timing,
    load_pattern_sequence,
    prepare_dlpc900_for_video_pattern,
    start_loaded_pattern_sequences,
)
from dmdcontrol.support.constants import (
    BITPLANES,
    DEFAULT_HZ,
    DEFAULT_SEQUENCE_UTILIZATION,
    DMD_HEIGHT,
    DMD_WIDTH,
)
from dmdcontrol.support.logging import logger, setup_logger


@dataclass(frozen=True)
class PairConfig:
    dmd_a: DmdMapping
    dmd_b: DmdMapping
    desktop_width: int = PAIR_WIDTH
    desktop_height: int = PAIR_HEIGHT
    offset_b: tuple[int, int] = OFFSET_B
    offset_a: tuple[int, int] = OFFSET_A
    target_hz: int = DEFAULT_HZ


class _DryRunDLPC:
    def get_display_dimensions(self):
        return None


def _positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _nonnegative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _parse_numbers(value):
    try:
        numbers = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("numbers must be decimal digits") from exc
    if not numbers:
        raise argparse.ArgumentTypeError("numbers must not be empty")
    if any(number < 1 or number > 9 for number in numbers):
        raise argparse.ArgumentTypeError("numbers must be in the range 1..9")
    return numbers


def _parse_numbers_bitplane_order(value):
    try:
        order = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("numbers bitplane order must be decimal indexes") from exc
    if not order:
        raise argparse.ArgumentTypeError("numbers bitplane order must not be empty")
    if any(index < 0 for index in order):
        raise argparse.ArgumentTypeError("numbers bitplane order indexes must be non-negative")
    return order


def resolve_pair_config(config_path=None, target_hz=None):
    dmd_a = resolve_dmd_mapping("A", config_path)
    dmd_b = resolve_dmd_mapping("B", config_path)
    for mapping in (dmd_a, dmd_b):
        if not mapping.xrandr_output:
            raise ValueError(
                f"DMD {mapping.name} must define xrandr_output for paired runs."
            )
        if not mapping.usb_id_path:
            raise ValueError(
                f"DMD {mapping.name} must define usb_id_path for paired runs."
            )

    configured_hz = {
        hz for hz in (dmd_a.target_hz, dmd_b.target_hz) if hz is not None
    }
    if len(configured_hz) > 1:
        raise ValueError(
            f"Paired DMD target_hz values must match, got {sorted(configured_hz)}"
        )
    resolved_hz = int(target_hz or next(iter(configured_hz), DEFAULT_HZ))
    return PairConfig(dmd_a=dmd_a, dmd_b=dmd_b, target_hz=resolved_hz)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Dual DLPC900 paired Video Pattern Mode runtime"
    )
    parser.add_argument("--hz", type=int, default=None, help=f"Target Hz, default from dmd_devices.json or {DEFAULT_HZ}")
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
    parser.add_argument("--runtime-seconds", type=int, default=60)
    parser.add_argument(
        "--a-calibr-square-control-file",
        default=None,
        help="Control-file path for DMD A calibration-square edits in paired calibration-dot mode",
    )
    parser.add_argument("--b-dot-x", type=int, default=DMD_WIDTH // 2)
    parser.add_argument("--b-dot-y", type=int, default=DMD_HEIGHT // 2)
    parser.add_argument("--b-dot-radius", type=_positive_int, default=40)
    parser.add_argument(
        "--dot-radius",
        type=_positive_int,
        default=40,
        help="Radius for generic static dot frames, for example --test dot",
    )
    parser.add_argument(
        "--b-dot-shape",
        choices=("circle", "square"),
        default="circle",
    )
    parser.add_argument("--b-dot-invert", action="store_true")
    parser.add_argument(
        "--kernel-px",
        type=_positive_int,
        default=30,
        help="A-kernel paired recipe: total 3x3 kernel side length in pixels",
    )
    parser.add_argument(
        "--kernel-exposure-us",
        type=_positive_int,
        default=None,
        help="A-kernel paired recipe: uniform exposure per kernel bitplane",
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
        type=_nonnegative_int,
        default=3,
        help="A-kernel paired recipe: all-black VSYNC frames prepended to each cycle",
    )
    parser.add_argument(
        "--numbers",
        type=_parse_numbers,
        default=_parse_numbers("1,2,3,4,5"),
        help="Numbers paired recipe: comma-separated sequence of digits 1..9",
    )
    parser.add_argument(
        "--numbers-exposure-us",
        type=_positive_int,
        default=None,
        help="Numbers paired recipe: optional per-bitplane LUT exposure override",
    )
    parser.add_argument(
        "--numbers-size-px",
        type=_positive_int,
        default=None,
        help="Numbers paired recipe: seven-segment digit height in pixels",
    )
    parser.add_argument(
        "--numbers-bitplane-order",
        type=_parse_numbers_bitplane_order,
        default=None,
        help=(
            "Numbers paired recipe: zero-based bitplane indexes in chronological "
            "display order. Use 1,2,3,4,0 if the first five captured triggers "
            "visually show 2,3,4,5,1 for --numbers 1,2,3,4,5."
        ),
    )
    parser.add_argument(
        "--count-start",
        type=_positive_int,
        default=1,
        help="A-count paired recipe: first integer label to display",
    )
    parser.add_argument(
        "--count-end",
        type=_positive_int,
        default=100,
        help="A-count paired recipe: final integer label to display, inclusive",
    )
    parser.add_argument(
        "--count-slots-per-frame",
        type=int,
        default=2,
        help="A-count paired recipe: count labels packed into bitplanes per VSYNC frame",
    )
    parser.add_argument(
        "--count-exposure-us",
        type=_positive_int,
        default=None,
        help="A-count paired recipe: optional per-count LUT exposure override",
    )
    parser.add_argument("--wake-dp", action="store_true", help="Wake both DP receivers before runtime")
    parser.add_argument(
        "--dual-pixel",
        action="store_true",
        help="Force dual-pixel P1-P2 mode on both DLPC900 controllers",
    )
    parser.add_argument(
        "--seq-utilization",
        type=float,
        default=DEFAULT_SEQUENCE_UTILIZATION,
        help="Fraction of safe frame budget allocated to LUT exposure timing",
    )
    parser.add_argument(
        "--trig2-frame-zero",
        action="store_true",
        help="Emit TRIG_OUT_2 only for bitplane/frame-zero anchor entries",
    )
    parser.add_argument(
        "--trigger-out-2-delay-fraction",
        type=float,
        default=0.00,
        help="Fraction of LUT exposure used as TRIG_OUT_2 rising-edge delay. Default: 0.",
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
        type=float,
        default=1.0,
        help="Maximum live-preview POST rate when --preview-url is set",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def _validate_pair_args(args):
    if args.preview_fps <= 0:
        raise SystemExit("--preview-fps must be positive")
    if not math.isfinite(args.trigger_out_2_delay_fraction):
        raise SystemExit("--trigger-out-2-delay-fraction must be finite")
    if args.trigger_out_2_delay_fraction < 0:
        raise SystemExit("--trigger-out-2-delay-fraction must be non-negative")
    if args.test == KERNEL_STATIC_PAIR_TEST:
        if args.test_a:
            raise SystemExit("--test-a is not valid for a-kernel-b-static; A is the kernel stream")
        return
    if _is_count_recipe(args.test):
        _validate_count_recipe_args(args)
        return
    if _is_numbers_recipe(args.test):
        if args.test == A_NUMBERS_B_STATIC_PAIR_TEST and args.test_a:
            raise SystemExit("--test-a is not valid for a-numbers-b-static; A is the numbers stream")
        if len(args.numbers) > BITPLANES:
            raise SystemExit(f"--numbers can contain at most {BITPLANES} entries")
        if args.numbers_bitplane_order is not None:
            if len(args.numbers_bitplane_order) != len(args.numbers):
                raise SystemExit("--numbers-bitplane-order length must match --numbers length")
            if sorted(args.numbers_bitplane_order) != list(range(len(args.numbers))):
                raise SystemExit(
                    "--numbers-bitplane-order must be a zero-based permutation of --numbers slots"
                )
        return
    if args.test not in STATIC_PAIR_TESTS and (args.test_a or args.test_b):
        raise SystemExit("--test-a/--test-b are only valid for static paired tests")


def _is_numbers_recipe(test):
    return test in (NUMBER_PAIR_TEST, A_NUMBERS_B_STATIC_PAIR_TEST)


def _is_count_recipe(test):
    return test == A_COUNT_B_STATIC_PAIR_TEST


def _validate_count_recipe_args(args):
    if args.test_a:
        raise SystemExit("--test-a is not valid for a-count-b-static; A is the count stream")
    if args.count_start > args.count_end:
        raise SystemExit("--count-start must be <= --count-end")
    if args.count_slots_per_frame <= 0 or args.count_slots_per_frame > BITPLANES:
        raise SystemExit(f"--count-slots-per-frame must be in the range 1..{BITPLANES}")
    count_total = args.count_end - args.count_start + 1
    if count_total % args.count_slots_per_frame != 0:
        raise SystemExit("count range length must be divisible by --count-slots-per-frame")
    frame_count = count_total // args.count_slots_per_frame
    if frame_count > MAX_COUNT_SEQUENCE_FRAMES:
        raise SystemExit(
            f"a-count-b-static can span at most {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames"
        )


def _kernel_lut_override(args, target_hz):
    return compute_kernel_lut_override(
        enabled=args.test == KERNEL_STATIC_PAIR_TEST,
        kernel_exposure_us=args.kernel_exposure_us,
        target_hz=target_hz,
        sequence_utilization=args.seq_utilization,
        dark_time_us=getattr(args, "dark_time_us", None),
    )


def _lut_override(args, target_hz):
    if _is_numbers_recipe(args.test):
        # The numbers recipe packs only the requested digits into the first N
        # video bitplanes. The LUT must expose exactly those N bitplanes, not
        # all 24 possible RGB bitplanes. Forcing BITPLANES makes long exposures
        # impossible at 60 Hz; e.g. 24 * 3000 us.
        return len(args.numbers), args.numbers_exposure_us
    if _is_count_recipe(args.test):
        return args.count_slots_per_frame, args.count_exposure_us
    return _kernel_lut_override(args, target_hz)


def _numbers_provider_kwargs(args):
    return {
        "test_b": args.test_b,
        "numbers": args.numbers,
        "numbers_size_px": args.numbers_size_px,
        "numbers_bitplane_order": getattr(args, "numbers_bitplane_order", None),
        "numbers_exposure_us": args.numbers_exposure_us,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "b_dot_shape": args.b_dot_shape,
        "b_dot_invert": args.b_dot_invert,
        "width": DMD_WIDTH,
        "height": DMD_HEIGHT,
    }


def _count_provider_kwargs(args):
    return {
        "test_b": args.test_b,
        "count_start": args.count_start,
        "count_end": args.count_end,
        "count_slots_per_frame": args.count_slots_per_frame,
        "numbers_size_px": args.numbers_size_px,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "b_dot_shape": args.b_dot_shape,
        "b_dot_invert": args.b_dot_invert,
        "width": DMD_WIDTH,
        "height": DMD_HEIGHT,
    }


def _make_runtime_pair_frame_provider(args, engine, target_hz):
    if args.test == CALIBRATION_DOT_PAIR_TEST:
        single_a = SingleDmdFrameAdapter(
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            window=engine.window,
        )
        initial_state = default_calibration_square_state(DMD_WIDTH, DMD_HEIGHT)
        initial_frame = build_calibration_square_frame(single_a, initial_state)
        frame_provider_a = make_calibration_square_frame_provider(
            single_a,
            initial_frame,
            control_file=args.a_calibr_square_control_file,
            initial_state=initial_state,
        )
        frame_b = generate_dot_frame(
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            x=args.b_dot_x,
            y=args.b_dot_y,
            radius=args.b_dot_radius,
            shape=args.b_dot_shape,
            invert=args.b_dot_invert,
        )
        return CalibrationSquareDotPairFrameProvider(
            frame_provider_a,
            frame_b,
            initial_frame_a=initial_frame,
            flicker_a=True,
        )

    if args.test == KERNEL_STATIC_PAIR_TEST:
        single_a = SingleDmdFrameAdapter(
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            window=engine.window,
        )
        entries_count, _ = _kernel_lut_override(args, target_hz)
        slots = entries_count or BITPLANES
        kernel_frames, metadata = build_kernel_frames(
            single_a,
            kernel_px=args.kernel_px,
            slots_per_frame=slots,
            leader_frames=args.kernel_leader_frames,
            blank_end_frame=args.kernel_blank_end_frame,
        )
        logger.info(
            f"[+] A-kernel frames ready: {metadata['cycle_vsyncs']} VSYNC frames per cycle "
            f"({metadata['leader_frames']} leader + {metadata['payload_vsyncs']} payload/end-marker), "
            f"{metadata['cycle_fires']} bitplane fires."
        )
        frame_provider_a = KernelFrameProvider(
            kernel_frames,
            black_frame=metadata["black_frame"],
            single_shot=args.kernel_single_shot,
        )
        frame_b = generate_static_frame(
            args.test_b or "checkerboard",
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            route_label="B",
            dot_x=args.b_dot_x,
            dot_y=args.b_dot_y,
            dot_radius=args.b_dot_radius,
            dot_shape=args.b_dot_shape,
            dot_invert=args.b_dot_invert,
        )
        return DynamicAStaticBPairFrameProvider(
            frame_provider_a,
            frame_b,
            initial_frame_a=kernel_frames[0],
        )

    if args.test in STATIC_PAIR_TESTS:
        return make_pair_frame_provider(
            args.test,
            test_a=args.test_a,
            test_b=args.test_b,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
            dot_radius=args.dot_radius,
        )
    if _is_numbers_recipe(args.test):
        return make_pair_frame_provider(args.test, **_numbers_provider_kwargs(args))
    if _is_count_recipe(args.test):
        return make_pair_frame_provider(args.test, **_count_provider_kwargs(args))
    return make_pair_frame_provider(args.test, width=DMD_WIDTH, height=DMD_HEIGHT)


def _dry_run_timing(args, pair_config):
    entries_count, exposure_us = _lut_override(args, pair_config.target_hz)
    entries, timing = build_lut_entries(
        _DryRunDLPC(),
        pair_config.target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=exposure_us,
        dark_time_us=args.dark_time_us,
    )
    logger.info("[DRY RUN] Hardware was not opened. OpenGL and USB modules were not imported.")
    logger.info(
        f"[DRY RUN] X layout: {pair_config.desktop_width}x{pair_config.desktop_height}; "
        f"B {pair_config.dmd_b.xrandr_output} at +{pair_config.offset_b[0]}+{pair_config.offset_b[1]}, "
        f"A {pair_config.dmd_a.xrandr_output} at +{pair_config.offset_a[0]}+{pair_config.offset_a[1]}."
    )
    logger.info(
        f"[DRY RUN] USB: A id_path={pair_config.dmd_a.usb_id_path}, "
        f"B id_path={pair_config.dmd_b.usb_id_path}."
    )
    if args.test == CALIBRATION_DOT_PAIR_TEST:
        logger.info(
            f"[DRY RUN] Pair content: A=calibr-square control_file="
            f"{args.a_calibr_square_control_file or '(none)'}, "
            f"flicker=every-other-frame, "
            f"B=dot x={args.b_dot_x}, y={args.b_dot_y}, radius={args.b_dot_radius}, "
            f"shape={args.b_dot_shape}, invert={args.b_dot_invert}."
        )
    elif args.test == KERNEL_STATIC_PAIR_TEST:
        slots = timing["entries_count"]
        pad = (slots - (512 % slots)) % slots
        payload_vsyncs = (512 + pad) // slots
        end_marker_vsyncs = 1 if args.kernel_blank_end_frame else 0
        cycle_vsyncs = args.kernel_leader_frames + payload_vsyncs + end_marker_vsyncs
        logger.info(
            f"[DRY RUN] Pair content: A=kernel kernel_px={args.kernel_px}, "
            f"leader_frames={args.kernel_leader_frames}, blank_end_frame={args.kernel_blank_end_frame}, "
            f"single_shot={args.kernel_single_shot}; B={args.test_b or 'checkerboard'} static."
        )
        logger.info(
            f"[DRY RUN] A-kernel cycle: {cycle_vsyncs} VSYNC frames, "
            f"{args.kernel_leader_frames * slots} leader fires, 512 kernels, {pad} pad fires"
            f"{', ' + str(slots) + ' end-marker fires' if args.kernel_blank_end_frame else ''}."
        )
    elif _is_numbers_recipe(args.test):
        logger.info(
            f"[DRY RUN] Pair content: numbers={','.join(str(n) for n in args.numbers)}, "
            f"bitplane_order={','.join(str(i) for i in args.numbers_bitplane_order) if args.numbers_bitplane_order is not None else 'default'}, "
            f"per-bitplane exposure={args.numbers_exposure_us or timing['exposure_us']}us, "
            f"size_px={args.numbers_size_px or 'default'} on both DMDs."
        )
    elif _is_count_recipe(args.test):
        payload_vsyncs = count_sequence_frame_count(
            args.count_start,
            args.count_end,
            args.count_slots_per_frame,
        )
        logger.info(
            f"[DRY RUN] Pair content: A=count {args.count_start}..{args.count_end}, "
            f"slots_per_frame={args.count_slots_per_frame}, "
            f"per-count exposure={args.count_exposure_us or timing['exposure_us']}us, "
            f"payload_vsyncs={payload_vsyncs}; B={args.test_b or 'dot'} static."
        )
    elif args.test in STATIC_PAIR_TESTS:
        logger.info(
            f"[DRY RUN] Pair content: test={args.test}, test_a={args.test_a or args.test}, "
            f"test_b={args.test_b or args.test}, dot_radius={args.dot_radius}."
        )
    else:
        logger.info(
            f"[DRY RUN] Pair content: dynamic test={args.test}, one shared frame index/timebase."
        )
    logger.info(
        f"[DRY RUN] Pattern LUT: {len(entries)} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/"
        f"{timing['usable_frame_period_us']:.1f}us usable, "
        f"effective VSYNC={timing['effective_frame_hz']:.3f}Hz."
    )
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 mode: {timing['trig2_mode']}; expected pulses/s="
        f"{timing['effective_frame_hz'] if args.trig2_frame_zero else timing['effective_binary_rate_hz']:.1f}."
    )
    trigger_timing = compute_trigger_out_2_timing(
        timing["exposure_us"],
        delay_fraction=args.trigger_out_2_delay_fraction,
    )
    timing["trigger_out_2"] = trigger_timing
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 rising edge delay={trigger_timing['rising_delay_us']}us, "
        f"falling={trigger_timing['falling_delay_us']}us "
        f"({trigger_timing['delay_fraction']:.3f} of {trigger_timing['delay_basis']})."
    )


def _live_preview_metadata_for_frame(base_metadata, provider):
    metadata = dict(base_metadata or {})
    frame_index = getattr(provider, "frame_index", None)
    if frame_index is not None:
        metadata["source_frame_index"] = int(frame_index)
    return metadata


def _build_live_preview_metadata(args, pair_config, state_a, state_b):
    lut_state = state_a or state_b
    metadata = {
        "layout": "pair",
        "test": args.test,
        "test_a": args.test_a,
        "test_b": args.test_b,
        "routes": {
            "B": {
                "position": "left",
                "xrandr_output": pair_config.dmd_b.xrandr_output,
                "offset": list(pair_config.offset_b),
            },
            "A": {
                "position": "right",
                "xrandr_output": pair_config.dmd_a.xrandr_output,
                "offset": list(pair_config.offset_a),
            },
        },
        "target_hz": pair_config.target_hz,
    }
    if _is_numbers_recipe(args.test):
        metadata["numbers"] = {
            "sequence": list(args.numbers),
            "exposure_us": args.numbers_exposure_us,
            "size_px": args.numbers_size_px,
        }
    if _is_count_recipe(args.test):
        metadata["count"] = {
            "start": args.count_start,
            "end": args.count_end,
            "slots_per_frame": args.count_slots_per_frame,
            "exposure_us": args.count_exposure_us,
        }
    if lut_state:
        metadata["lut"] = build_lut_preview_metadata(lut_state["entries"], lut_state["timing"])
        metadata["lut_applies_to"] = ["A", "B"]
    return metadata


def _run_pair_render_loop(
        dlpc_a,
        dlpc_b,
        engine,
        provider,
        args,
        preview_poster=None,
        preview_metadata=None,
):
    end_t = None if args.runtime_seconds <= 0 else time.time() + args.runtime_seconds
    while (end_t is None or time.time() < end_t) and not engine.should_close():
        frame_a, frame_b = provider.next_pair()
        engine.display_pair(frame_a, frame_b)
        if preview_poster is not None:
            preview_poster.maybe_post_pair(
                frame_a,
                frame_b,
                metadata=_live_preview_metadata_for_frame(preview_metadata, provider),
            )


def _start_pair_pump(engine, provider):
    pump_event = threading.Event()
    pump_ready = threading.Event()
    frame_a, frame_b = provider.initial_pair()

    def _continuous_pump():
        engine.make_context_current()
        pump_ready.set()
        try:
            while pump_event.is_set():
                engine.display_pair(frame_a, frame_b)
        finally:
            engine.release_context()

    engine.release_context()
    pump_event.set()
    thread = threading.Thread(target=_continuous_pump, daemon=True)
    thread.start()
    pump_ready.wait(timeout=1.0)
    time.sleep(0.1)
    return pump_event, thread


def _stop_pair_pump(engine, pump_event, pump_thread):
    if pump_event is not None:
        pump_event.clear()
    if pump_thread is not None:
        pump_thread.join(timeout=1.0)
    engine.make_context_current()


def _run_prepared_pair(args, pair_config, before_sequencer_start=None):
    lut_entries_count, lut_per_entry_exposure_us = _lut_override(
        args,
        pair_config.target_hz,
    )

    from dmdcontrol.hardware.dlpc900 import DLPC900
    from dmdcontrol.patterns.paired import PairedPatternEngine

    logger.info(
        f"[+] Paired DMD layout: B {pair_config.dmd_b.xrandr_output} left +0+0, "
        f"A {pair_config.dmd_a.xrandr_output} right +{DMD_WIDTH}+0"
    )
    engine = None
    dlpc_a = None
    dlpc_b = None
    pump_event = None
    pump_thread = None
    preview_poster = None
    try:
        engine = PairedPatternEngine(fps=pair_config.target_hz)
        provider = _make_runtime_pair_frame_provider(args, engine, pair_config.target_hz)
        if args.preview_url:
            preview_poster = LivePreviewPoster(args.preview_url, fps=args.preview_fps)
        dlpc_a = DLPC900(
            usb_id_path=pair_config.dmd_a.usb_id_path,
            usb_devpath_contains=pair_config.dmd_a.usb_devpath_contains,
        )
        dlpc_b = DLPC900(
            usb_id_path=pair_config.dmd_b.usb_id_path,
            usb_devpath_contains=pair_config.dmd_b.usb_devpath_contains,
        )

        if args.wake_dp:
            for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
                logger.info(f"[+] Waking DisplayPort receiver for DMD {label}...")
                dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        logger.info("[+] Starting paired continuous GL pump before DLPC preparation...")
        pump_event, pump_thread = _start_pair_pump(engine, provider)

        logger.info("[+] Preparing DMD A controller without starting sequencer...")
        state_a = prepare_dlpc900_for_video_pattern(
            dlpc_a,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
            entries_count=lut_entries_count,
            per_entry_exposure_us=lut_per_entry_exposure_us,
            trigger_out_2_delay_fraction=args.trigger_out_2_delay_fraction,
            dark_time_us=args.dark_time_us,
        )
        logger.info("[+] Preparing DMD B controller without starting sequencer...")
        state_b = prepare_dlpc900_for_video_pattern(
            dlpc_b,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
            entries_count=lut_entries_count,
            per_entry_exposure_us=lut_per_entry_exposure_us,
            trigger_out_2_delay_fraction=args.trigger_out_2_delay_fraction,
            dark_time_us=args.dark_time_us,
        )

        logger.info("[+] Loading paired pattern LUTs without starting sequencers...")
        load_pattern_sequence(dlpc_a, state_a["entries"])
        load_pattern_sequence(dlpc_b, state_b["entries"])
        live_preview_metadata = _build_live_preview_metadata(args, pair_config, state_a, state_b)

        if before_sequencer_start is not None:
            before_sequencer_start({
                "args": args,
                "pair_config": pair_config,
                "state_a": state_a,
                "state_b": state_b,
                "preview_metadata": live_preview_metadata,
            })

        logger.info("[+] Starting both DLPC900 sequencers from paired software barrier...")
        start_loaded_pattern_sequences(dlpc_a, dlpc_b, post_start_delay_s=0.0, verify=True)
        logger.info("[SCOPE] Compare TRIG_OUT_2_A and TRIG_OUT_2_B for start skew and drift.")

        _stop_pair_pump(engine, pump_event, pump_thread)
        pump_event = None
        pump_thread = None

        first_a, first_b = provider.initial_pair()
        engine.display_pair(first_a, first_b)
        if preview_poster is not None:
            preview_poster.maybe_post_pair(
                first_a,
                first_b,
                metadata=_live_preview_metadata_for_frame(live_preview_metadata, provider),
                force=True,
            )
        _run_pair_render_loop(
            dlpc_a,
            dlpc_b,
            engine,
            provider,
            args,
            preview_poster=preview_poster,
            preview_metadata=live_preview_metadata,
        )
        return 0
    finally:
        if preview_poster is not None:
            preview_poster.close()
        if engine is not None and pump_event is not None:
            _stop_pair_pump(engine, pump_event, pump_thread)
        for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            if dlpc is None:
                continue
            try:
                logger.info(f"[-] Stopping DMD {label} pattern display...")
                dlpc.start_pattern_display(0)
                dlpc.set_display_mode(0x00)
                dlpc.apply_block_lock_workaround()
            except Exception as cleanup_exc:
                logger.warning(f"DMD {label} cleanup warning: {cleanup_exc}")
            close = getattr(dlpc, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as close_exc:
                    logger.warning(f"DMD {label} close warning: {close_exc}")
        if engine is not None:
            engine.cleanup()


def run_with_before_start_callback(argv, before_start):
    args = _build_parser().parse_args(argv)
    setup_logger(verbosity=args.verbose)
    pair_config = resolve_pair_config(args.dmd_config, target_hz=args.hz)
    _validate_pair_args(args)
    if args.dry_run_timing:
        _dry_run_timing(args, pair_config)
        return 0
    return _run_prepared_pair(args, pair_config, before_sequencer_start=before_start)


def main(argv=None):
    args = _build_parser().parse_args(argv)
    setup_logger(verbosity=args.verbose)
    pair_config = resolve_pair_config(args.dmd_config, target_hz=args.hz)
    _validate_pair_args(args)

    if args.dry_run_timing:
        _dry_run_timing(args, pair_config)
        return 0

    return _run_prepared_pair(args, pair_config)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception(f"[ERROR] {exc}")
        raise SystemExit(1)
