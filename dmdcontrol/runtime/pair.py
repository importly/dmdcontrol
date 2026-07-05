"""Paired dual-DMD runtime for one 3840x1080 OpenGL swap loop."""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass

import numpy as np

from dmdcontrol.hardware.mapping import DmdMapping, resolve_dmd_mapping
from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    OFFSET_A,
    OFFSET_B,
    PAIR_HEIGHT,
    PAIR_TESTS,
    PAIR_WIDTH,
    STATIC_IMAGES_PAIR_TEST,
    STATIC_PAIR_TESTS,
    FramePair,
    as_frame_pair,
)
from dmdcontrol.preview.render import LivePreviewPoster, build_lut_preview_metadata
from dmdcontrol.runtime.count_slots import (
    CountSequenceConfig,
    resolve_count_slots_per_frame,
)
from dmdcontrol.runtime.display_sequence import build_paired_display_sequence
from dmdcontrol.runtime.lifecycle import (
    compute_trigger_out_2_timing,
    load_pattern_sequence,
    prepare_dlpc900_for_video_pattern,
    start_loaded_pattern_sequences,
)
from dmdcontrol.runtime.lifecycle import (
    warn_dark_time_video_pattern_mode as _warn_dark_time_video_pattern_mode,
)
from dmdcontrol.support.argparse_types import (
    count_slots_per_frame,
    nonnegative_int,
    positive_int,
    trigger_out_rising_delay_us,
)
from dmdcontrol.support.constants import (
    DEFAULT_HZ,
    DEFAULT_SEQUENCE_UTILIZATION,
    DMD_HEIGHT,
    DMD_WIDTH,
)
from dmdcontrol.support.logging import logger, setup_logger

PAIRED_STARTUP_LEADER_VSYNCS = 16


@dataclass(frozen=True)
class PairConfig:
    dmd_a: DmdMapping
    dmd_b: DmdMapping
    desktop_width: int = PAIR_WIDTH
    desktop_height: int = PAIR_HEIGHT
    offset_b: tuple[int, int] = OFFSET_B
    offset_a: tuple[int, int] = OFFSET_A
    target_hz: int = DEFAULT_HZ


def _blank_dmd_frame():
    return np.zeros((DMD_HEIGHT, DMD_WIDTH, 3), dtype=np.uint8)


def _blank_pair_frames():
    return FramePair(a=_blank_dmd_frame(), b=_blank_dmd_frame())


def resolve_pair_config(config_path=None):
    dmd_a = resolve_dmd_mapping("A", config_path)
    dmd_b = resolve_dmd_mapping("B", config_path)
    for mapping in (dmd_a, dmd_b):
        if not mapping.xrandr_output:
            raise ValueError(f"DMD {mapping.name} must define xrandr_output for paired runs.")
        if not mapping.usb_id_path:
            raise ValueError(f"DMD {mapping.name} must define usb_id_path for paired runs.")

    return PairConfig(dmd_a=dmd_a, dmd_b=dmd_b)


def _build_parser():
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
    parser.add_argument("--runtime-seconds", type=int, default=60)
    parser.add_argument(
        "--a-calibr-square-control-file",
        default=None,
        help="Control-file path for DMD A calibration-square edits in paired calibration-dot mode",
    )
    parser.add_argument("--b-dot-x", type=int, default=DMD_WIDTH // 2)
    parser.add_argument("--b-dot-y", type=int, default=DMD_HEIGHT // 2)
    parser.add_argument("--b-dot-radius", type=positive_int, default=40)
    parser.add_argument(
        "--dot-radius",
        type=positive_int,
        default=40,
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
        default=30,
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
        default=3,
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
        default=1,
        help="A-count paired recipe: first integer label to display",
    )
    parser.add_argument(
        "--count-end",
        type=positive_int,
        default=100,
        help="A-count paired recipe: final integer label to display, inclusive",
    )
    parser.add_argument(
        "--count-slots-per-frame",
        type=count_slots_per_frame,
        default=None,
        help=(
            "A-count paired recipe: count labels packed into bitplanes per VSYNC frame. "
            "Use 'auto' or omit to choose the fastest timing-valid divisor."),
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
        "--paired-startup-leader-vsyncs",
        type=nonnegative_int,
        default=PAIRED_STARTUP_LEADER_VSYNCS,
        help=(
            "Blank paired source VSYNCs displayed after both sequencers start "
            "before the first semantic frame. These trigger pulses are recorded "
            "in startup_leader metadata and skipped by camera artifact generation."),
    )
    parser.add_argument(
        "--trigger-out-2-rising-delay-us",
        type=trigger_out_rising_delay_us,
        default=0,
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
        type=float,
        default=1.0,
        help="Maximum live-preview POST rate when --preview-url is set",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def _is_count_recipe(test):
    return test == A_COUNT_B_STATIC_PAIR_TEST


def _resolve_count_recipe_args(args, target_hz=DEFAULT_HZ):
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


def _validate_pair_args(args, target_hz=DEFAULT_HZ):
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


def _validate_count_recipe_args(args, target_hz=DEFAULT_HZ):
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


def _dry_run_timing(args, pair_config):
    sequence = build_paired_display_sequence(
        args,
        target_hz=pair_config.target_hz,
        engine=None,
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
    )
    entries = sequence.lut_entries()
    timing = dict(sequence.timing)
    startup_leader = sequence.startup_leader_metadata()
    logger.info(
        f"[DRY RUN] Display sequence: {len(sequence.frames)} source frames, "
        f"{len(sequence.lut_slots)} LUT slots per source frame, "
        f"startup_policy={sequence.startup_policy.mode}, "
        f"startup_leader_triggers={startup_leader['trigger_count']}.")
    logger.info("[DRY RUN] Hardware was not opened. OpenGL and USB modules were not imported.")
    logger.info(
        f"[DRY RUN] X layout: {pair_config.desktop_width}x{pair_config.desktop_height}; "
        f"B {pair_config.dmd_b.xrandr_output} at +{pair_config.offset_b[0]}+{pair_config.offset_b[1]}, "
        f"A {pair_config.dmd_a.xrandr_output} at +{pair_config.offset_a[0]}+{pair_config.offset_a[1]}."
    )
    logger.info(
        f"[DRY RUN] USB: A id_path={pair_config.dmd_a.usb_id_path}, "
        f"B id_path={pair_config.dmd_b.usb_id_path}.")
    if args.test == CALIBRATION_DOT_PAIR_TEST:
        logger.info(
            f"[DRY RUN] Pair content: A=calibr-square control_file="
            f"{args.a_calibr_square_control_file or '(none)'}, "
            f"flicker=every-other-frame, "
            f"B=dot x={args.b_dot_x}, y={args.b_dot_y}, radius={args.b_dot_radius}, "
            f"shape={args.b_dot_shape}, invert={args.b_dot_invert}.")
    elif args.test == KERNEL_STATIC_PAIR_TEST:
        kernel_metadata = sequence.mode_metadata.get("kernel", {})
        slots = timing["entries_count"]
        pad = int(kernel_metadata.get("pad_fires", (slots - (512 % slots)) % slots))
        payload_vsyncs = int(kernel_metadata.get("payload_vsyncs", (512 + pad) // slots))
        cycle_vsyncs = int(
            kernel_metadata.get(
                "cycle_vsyncs",
                args.kernel_leader_frames + payload_vsyncs +
                (1 if args.kernel_blank_end_frame else 0),
            ))
        logger.info(
            f"[DRY RUN] Pair content: A=kernel kernel_px={args.kernel_px}, "
            f"leader_frames={args.kernel_leader_frames}, blank_end_frame={args.kernel_blank_end_frame}, "
            f"single_shot={args.kernel_single_shot}; B={args.test_b or 'checkerboard'} static.")
        logger.info(
            f"[DRY RUN] A-kernel cycle: {cycle_vsyncs} VSYNC frames, "
            f"{args.kernel_leader_frames * slots} leader fires, 512 kernels, {pad} pad fires"
            f"{', ' + str(slots) + ' end-marker fires' if args.kernel_blank_end_frame else ''}.")
    elif _is_count_recipe(args.test):
        count_config = CountSequenceConfig.from_args(args)
        startup_leader_vsyncs = sequence.startup_policy.leader_vsyncs
        logger.info(
            f"[DRY RUN] Pair content: A=count {args.count_start}..{args.count_end}, "
            f"slots_per_frame={count_config.count_slots_per_frame}, "
            f"blank_after_each_count={count_config.count_blank_between_frames}, "
            f"per-count exposure={args.exposure_us or timing['exposure_us']}us, "
            f"payload_vsyncs={count_config.frame_count}, "
            f"blank_lut_entries_per_vsync={count_config.blank_lut_entries_per_frame}; "
            f"B={args.test_b or 'dot'} static.")
        if sequence.startup_policy.mode == "prime_first_frame":
            logger.info(
                "[DRY RUN] Startup prime: first count/blank source frame is shown "
                "before sequencer start; blank startup leader triggers are disabled "
                f"(effective leader VSYNCs={startup_leader_vsyncs}).")
    elif args.test == STATIC_IMAGES_PAIR_TEST:
        logger.info(
            f"[DRY RUN] Pair content: A=image {args.static_image_a}, "
            f"B=image {args.static_image_b}, size_px={args.static_image_size_px}, "
            f"centered on black {DMD_WIDTH}x{DMD_HEIGHT} canvases.")
    elif args.test in STATIC_PAIR_TESTS:
        logger.info(
            f"[DRY RUN] Pair content: test={args.test}, test_a={args.test_a or args.test}, "
            f"test_b={args.test_b or args.test}, dot_radius={args.dot_radius}.")
    else:
        logger.info(
            f"[DRY RUN] Pair content: dynamic test={args.test}, one shared frame index/timebase.")
    logger.info(
        f"[DRY RUN] Pattern LUT: {len(entries)} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/"
        f"{timing['usable_frame_period_us']:.1f}us usable, "
        f"effective VSYNC={timing['effective_frame_hz']:.3f}Hz.")
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 mode: {timing['trig2_mode']}; expected pulses/s="
        f"{timing['effective_frame_hz'] if args.trig2_frame_zero else timing['effective_binary_rate_hz']:.1f}."
    )
    trigger_timing = compute_trigger_out_2_timing(
        rising_delay_us=args.trigger_out_2_rising_delay_us,
    )
    timing["trigger_out_2"] = trigger_timing
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 rising edge delay={trigger_timing['rising_delay_us']}us, "
        f"falling={trigger_timing['falling_delay_us']}us "
        f"(pulse width {trigger_timing['pulse_width_us']}us).")
    return 0

def _live_preview_metadata_for_frame(base_metadata, provider):
    metadata = dict(base_metadata or {})
    frame_index = getattr(provider, "frame_index", None)
    if frame_index is not None:
        metadata["source_frame_index"] = int(frame_index)
    return metadata


def _build_live_preview_metadata(args, pair_config, state_a, state_b, *, sequence=None):
    lut_state = state_a or state_b
    metadata = {
        "layout": "pair",
        "test": getattr(args, "test", None),
        "test_a": getattr(args, "test_a", None),
        "test_b": getattr(args, "test_b", None),
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
    if sequence is not None:
        metadata.update(sequence.preview_metadata())
        return metadata
    if _is_count_recipe(args.test):
        metadata["count"] = {
            **CountSequenceConfig.from_args(args).to_pair_preview_metadata(),
            "exposure_us": args.exposure_us,
        }
    if lut_state:
        metadata["lut"] = build_lut_preview_metadata(lut_state["entries"], lut_state["timing"])
        metadata["lut_applies_to"] = ["A", "B"]
    return metadata


def _display_frame_pair(engine, frame_pair):
    frames = as_frame_pair(frame_pair)
    engine.display_pair(frames.a, frames.b)


class PairRenderCoordinator:
    """Own one GL render thread from blank pre-start through semantic playback.

    The paired DLPC900 startup path is intentionally staged this way:
    1. Start one GL thread and keep both framebuffer halves on a blank pair while
       USB/DLPC setup is still happening. This keeps the DisplayPort pipeline
       active without advancing the semantic frame provider.
    2. Start both sequencers.
    3. Display a fixed number of blank startup-leader VSYNCs. Those VSYNCs create
       real TRIG_OUT_2 pulses, but they are intentionally non-semantic and are
       recorded in metadata as `startup_leader.trigger_count`.
    4. Only then request provider.initial_pair(), which should be the first real
       displayed frame such as count "1" / dot.

    Camera analysis must skip the startup-leader trigger count before labeling
    trigger windows. Otherwise the first blank leader pulse is mislabeled as the
    first displayed number, shifting the whole sequence.
    """

    def __init__(
        self,
        engine,
        provider,
        args,
        *,
        startup_leader_pair,
        startup_leader_vsyncs,
        preview_poster=None,
        preview_metadata=None,
    ):
        self.engine = engine
        self.provider = provider
        self.args = args
        self.startup_leader_pair = as_frame_pair(startup_leader_pair)
        self.startup_leader_vsyncs = int(startup_leader_vsyncs)
        self.preview_poster = preview_poster
        self.preview_metadata = preview_metadata
        self._ready = threading.Event()
        self._prime_first_semantic = threading.Event()
        self._prime_first_semantic_displayed = threading.Event()
        self._release_semantic = threading.Event()
        self._stop = threading.Event()
        self._error = None
        self._primed_first_semantic_pair = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.engine.release_context()
        self._thread.start()
        return self

    def wait_until_ready(self, timeout_s=1.0):
        ready = self._ready.wait(timeout=timeout_s)
        self._raise_if_failed()
        return ready

    def release_semantic_frames(self):
        self._release_semantic.set()

    def prime_first_semantic_frame(self, timeout_s=1.0):
        self._prime_first_semantic.set()
        displayed = self._prime_first_semantic_displayed.wait(timeout=timeout_s)
        self._raise_if_failed()
        return displayed

    def join(self):
        self._thread.join()
        self._raise_if_failed()

    def stop(self, timeout_s=1.0):
        self._stop.set()
        self._release_semantic.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout_s)

    def _raise_if_failed(self):
        if self._error is not None:
            raise self._error

    def _engine_should_close(self):
        should_close = getattr(self.engine, "should_close", None)
        return bool(should_close()) if should_close is not None else False

    def _run(self):
        try:
            self.engine.make_context_current()
            self._ready.set()
            # Nothing displayed before `release_semantic_frames()` is allowed to
            # consume provider frames. The sequencers may not be running yet, and
            # any triggers emitted during the startup leader are intentionally
            # blank and skipped by downstream camera processing.
            self._run_blank_until_released()
            self._run_startup_leader()
            self._run_semantic_frames()
        except BaseException as exc:
            self._error = exc
        finally:
            try:
                self.engine.release_context()
            except Exception:
                pass

    def _run_blank_until_released(self):
        while (
            not self._stop.is_set()
            and not self._release_semantic.is_set()
            and not self._engine_should_close()
        ):
            if self._prime_first_semantic.is_set():
                _display_frame_pair(self.engine, self._first_semantic_pair())
                self._prime_first_semantic_displayed.set()
            else:
                _display_frame_pair(self.engine, self.startup_leader_pair)

    def _run_startup_leader(self):
        for _ in range(max(0, self.startup_leader_vsyncs)):
            if self._stop.is_set() or self._engine_should_close():
                return
            _display_frame_pair(self.engine, self.startup_leader_pair)

    def _run_semantic_frames(self):
        end_t = None if self.args.runtime_seconds <= 0 else time.time() + self.args.runtime_seconds
        first_semantic_frame = True
        while (
            not self._stop.is_set()
            and (end_t is None or time.time() < end_t)
            and not self._engine_should_close()
        ):
            if first_semantic_frame:
                frame_pair = self._first_semantic_pair()
                first_semantic_frame = False
            else:
                frame_pair = as_frame_pair(self.provider.next_pair())
            _display_frame_pair(self.engine, frame_pair)
            if self.preview_poster is not None:
                self.preview_poster.maybe_post_pair(
                    frame_pair.a,
                    frame_pair.b,
                    metadata=_live_preview_metadata_for_frame(
                        self.preview_metadata,
                        self.provider,
                    ),
                )

    def _first_semantic_pair(self):
        if self._primed_first_semantic_pair is None:
            self._primed_first_semantic_pair = as_frame_pair(self.provider.initial_pair())
        return self._primed_first_semantic_pair


def _start_pair_render_coordinator(
    engine,
    provider,
    args,
    *,
    startup_leader_pair,
    startup_leader_vsyncs,
    preview_poster=None,
    preview_metadata=None,
):
    return PairRenderCoordinator(
        engine,
        provider,
        args,
        startup_leader_pair=startup_leader_pair,
        startup_leader_vsyncs=startup_leader_vsyncs,
        preview_poster=preview_poster,
        preview_metadata=preview_metadata,
    ).start()


def _run_prepared_pair(args, pair_config, before_sequencer_start=None):
    from dmdcontrol.hardware.dlpc900 import DLPC900
    from dmdcontrol.patterns.paired import PairedPatternEngine

    logger.info(
        f"[+] Paired DMD layout: B {pair_config.dmd_b.xrandr_output} left +0+0, "
        f"A {pair_config.dmd_a.xrandr_output} right +{DMD_WIDTH}+0")
    engine = None
    dlpc_a = None
    dlpc_b = None
    render_coordinator = None
    preview_poster = None
    try:
        engine = PairedPatternEngine(fps=pair_config.target_hz)
        sequence = build_paired_display_sequence(
            args,
            target_hz=pair_config.target_hz,
            engine=engine,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
        )
        provider = sequence.provider
        if provider is None:
            raise RuntimeError("paired display sequence did not provide a frame source")
        lut_entries = sequence.lut_entries()
        lut_entries_count = len(lut_entries)
        lut_per_entry_exposure_us = int(sequence.timing["exposure_us"])
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
                dlpc.wake_displayport_receiver()
            time.sleep(1.0)

        prime_first_semantic = sequence.startup_policy.mode == "prime_first_frame"
        startup_leader_pair = _blank_pair_frames()
        startup_leader_vsyncs = int(sequence.startup_policy.leader_vsyncs)
        logger.info(
            "[+] Starting paired continuous GL render coordinator with blank pre-start frames...")
        render_coordinator = _start_pair_render_coordinator(
            engine,
            provider,
            args,
            startup_leader_pair=startup_leader_pair,
            startup_leader_vsyncs=startup_leader_vsyncs,
        )
        if not render_coordinator.wait_until_ready(timeout_s=1.0):
            raise RuntimeError("Paired render coordinator did not become ready.")

        logger.info("[+] Preparing DMD A controller without starting sequencer...")
        state_a = prepare_dlpc900_for_video_pattern(
            dlpc_a,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
            entries_count=lut_entries_count,
            per_entry_exposure_us=lut_per_entry_exposure_us,
            trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
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
            trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
            dark_time_us=args.dark_time_us,
        )

        logger.info("[+] Loading paired pattern LUTs without starting sequencers...")
        load_pattern_sequence(dlpc_a, lut_entries)
        load_pattern_sequence(dlpc_b, lut_entries)
        state_a = {**state_a, "entries": lut_entries, "timing": dict(sequence.timing)}
        state_b = {**state_b, "entries": lut_entries, "timing": dict(sequence.timing)}
        live_preview_metadata = _build_live_preview_metadata(
            args,
            pair_config,
            state_a,
            state_b,
            sequence=sequence,
        )
        startup_leader = sequence.startup_leader_metadata()
        live_preview_metadata["startup_leader"] = startup_leader
        render_coordinator.preview_poster = preview_poster
        render_coordinator.preview_metadata = live_preview_metadata

        if before_sequencer_start is not None:
            before_sequencer_start(
                {
                    "args": args,
                    "pair_config": pair_config,
                    "state_a": state_a,
                    "state_b": state_b,
                    "preview_metadata": live_preview_metadata,
                    "startup_leader": startup_leader,
                    "display_sequence": sequence.metadata(),
                })

        if prime_first_semantic:
            logger.info(
                "[+] Priming first count/blank source frame before sequencer start...")
            if not render_coordinator.prime_first_semantic_frame(timeout_s=1.0):
                raise RuntimeError(
                    "Timed out priming first count/blank source frame before sequencer start.")

        logger.info("[+] Starting both DLPC900 sequencers from paired software barrier...")
        # Keep the startup-critical path short: HID readback verification can add
        # an unpredictable delay after one controller starts. The live GL thread
        # is already showing blanks, so we start both sequencers, release the
        # fixed blank leader, and then advance to provider.initial_pair().
        start_loaded_pattern_sequences(dlpc_a, dlpc_b, post_start_delay_s=0.0, verify=False)
        logger.info("[SCOPE] Compare TRIG_OUT_2_A and TRIG_OUT_2_B for start skew and drift.")
        render_coordinator.release_semantic_frames()
        render_coordinator.join()
        render_coordinator = None
        return 0
    finally:
        if preview_poster is not None:
            preview_poster.close()
        if render_coordinator is not None:
            render_coordinator.stop()
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


def _run_namespace(args, before_start=None):
    setup_logger(verbosity=args.verbose)
    pair_config = resolve_pair_config(args.dmd_config)
    _validate_pair_args(args, target_hz=pair_config.target_hz)
    _warn_dark_time_video_pattern_mode(args)
    if args.dry_run_timing:
        _dry_run_timing(args, pair_config)
        return 0
    return _run_prepared_pair(args, pair_config, before_sequencer_start=before_start)


def _run(argv, before_start=None):
    return _run_namespace(_build_parser().parse_args(argv), before_start)


def run_with_before_start_callback(argv, before_start):
    return _run(argv, before_start)


def run_with_before_start_namespace(args, before_start):
    return _run_namespace(args, before_start)


def run_namespace(args):
    return _run_namespace(args)


def main(argv=None):
    return _run(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception(f"[ERROR] {exc}")
        raise SystemExit(1)
