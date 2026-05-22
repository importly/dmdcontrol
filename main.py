import argparse
import threading
import time

try:
    import cv2
except ImportError:
    cv2 = None

from config import BITPLANES, DEFAULT_SEQUENCE_UTILIZATION, SAFE_MARGIN_US
from calibration_square_runtime import (
    build_calibration_square_frame,
    format_calibration_square_state,
    make_calibration_square_frame_provider,
)
from dlpc_lifecycle import (
    build_lut_entries,
    configure_dlpc900_for_video_pattern,
    log_board_snapshot,
    verify_runtime_state,
)
from dmd_config import resolve_dmd_mapping
from logger import logger, setup_logger
from pattern_modes import (
    DEFAULT_NUMBERS_EXPOSURE_US,
    NUMBER_SEQUENCE,
    PATTERN_NAMES,
    build_patterns,
    default_calibration_square_state,
    generate_number_rgb,
    number_index_for_elapsed,
)
from runtime_loop import run_render_loop, run_trigger_loop


def _build_parser():
    parser = argparse.ArgumentParser(description="DLPC900 1080p Video Pattern Runtime")
    parser.add_argument("--hz", type=int, default=60, help="Target Hz (60 or 120, experimental)")
    parser.add_argument("--monitor", type=int, default=None, help="GLFW monitor index")
    parser.add_argument("--dmd", default=None,
                        help="Configured DMD name from dmd_devices.json, for example A or B.")
    parser.add_argument("--dmd-config", default=None,
                        help="Path to DMD mapping config. Defaults to dmd_devices.json next to main.py.")
    parser.add_argument("--test", choices=PATTERN_NAMES, default="checkerboard",
                        help=f"Diagnostic pattern mode. Choices: {', '.join(PATTERN_NAMES)}.")
    parser.add_argument("--trigger", action="store_true", help="Software Trigger Mode (Approach A)")
    parser.add_argument("--runtime-seconds", type=int, default=60,
                        help="Runtime for diagnostic patterns. Use 0 to run until ESC/window close.")
    parser.add_argument("--wake-dp", action="store_true", help="Wake DP receiver in main.py")
    parser.add_argument("--dual-pixel", action="store_true",
                        help="Force dual-pixel P1-P2 mode for DLPC900 parallel input (default: single-pixel P1)")
    parser.add_argument("--seq-utilization", type=float, default=DEFAULT_SEQUENCE_UTILIZATION,
                        help="Fraction of safe frame budget allocated to LUT exposure timing (0<value<=1). "
                             "Lower values increase idle headroom and improve robustness.")
    parser.add_argument("--trig2-frame-zero", action="store_true",
                        help="Emit TRIG_OUT_2 only on LUT bitplane 0 (single frame anchor). "
                             "Default mode emits TRIG_OUT_2 on every bitplane.")
    parser.add_argument("--abort-recover-cooldown", type=float, default=8.0,
                        help="Seconds between automatic abort recovery attempts while watchdog detects sequencer abort.")
    parser.add_argument("--no-auto-recover-abort", action="store_true",
                        help="Disable automatic sequencer re-arm attempts when abort bit is detected during runtime.")
    parser.add_argument("--capture", type=str, help="Save the generated packed frames to an mp4 video (e.g. test.mp4)")
    parser.add_argument("--invert-dmd", action="store_true",
                        help="Invert the final packed DMD output: every pixel in every displayed bitplane. "
                             "This also inverts leader, pad, blank-end, and trigger black frames.")
    parser.add_argument("--kernel-px", type=int, default=30,
                        help="Total kernel side length in pixels for --test kernel (must be a multiple of 3). "
                             "Default 30 (3x3 cells of 10px). Use 999 for naked-eye visibility (3x3 cells of 333px).")
    parser.add_argument("--kernel-single-shot", action="store_true",
                        help="Play the kernel cycle once then hold the idle marker frame. Default: loop continuously.")
    parser.add_argument("--kernel-blank-end-frame", dest="kernel_blank_end_frame", action="store_true", default=True,
                        help="Append one all-black VSYNC frame (24 black bitplanes) at the end of each kernel cycle "
                             "as a sync marker for downstream DAQ. This is on by default.")
    parser.add_argument("--no-kernel-blank-end-frame", dest="kernel_blank_end_frame", action="store_false",
                        help="Disable the all-black VSYNC frame normally appended to each kernel cycle.")
    parser.add_argument("--kernel-leader-frames", type=int, default=3,
                        help="Number of all-black VSYNC frames prepended to each kernel cycle as an acquisition "
                             "leader marker. DAQ should ignore these initial trigger pulses. Default: 3.")
    parser.add_argument("--kernel-exposure-us", type=int, default=None,
                        help="Uniform exposure time in microseconds for every kernel (kernel mode only). "
                             "Default: use full 24-entry LUT (~615 us/kernel at 60 Hz with 0.90 utilization, "
                             "1440 Hz binary rate). Larger values reduce kernels per VSYNC and lengthen the "
                             "512-kernel cycle. "
                             "Ceiling = one VSYNC period (~16670 us at 60 Hz).")
    parser.add_argument("--numbers-exposure-us", type=int, default=None,
                        help="Wall-clock display time in microseconds for each digit in --test numbers. "
                             f"Default: {DEFAULT_NUMBERS_EXPOSURE_US} us.")
    parser.add_argument("--calibr-square-control-file", default=None,
                        help="Calibration-square only: read single-character controls from this file. "
                             "Used by run_calibr_square.sh; normal run_dmd.sh behavior is unchanged.")
    parser.add_argument("--dry-run-timing", action="store_true",
                        help="Print LUT, trigger, and kernel-cycle timing without opening OpenGL or USB hardware.")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase logging verbosity. Use -v for DEBUG logs and watchdog; -vv adds source paths "
                             "and full board snapshots.")
    return parser


class _DryRunDLPC:
    def get_display_dimensions(self):
        return None


def _compute_kernel_lut_override(args, target_hz):
    if args.test != "kernel" or args.kernel_exposure_us is None:
        return None, None
    frame_period_us = 1_000_000.0 / target_hz
    usable_us = (frame_period_us - SAFE_MARGIN_US) * args.seq_utilization
    entries_count = int(usable_us // args.kernel_exposure_us)
    entries_count = max(1, min(BITPLANES, entries_count))
    return entries_count, args.kernel_exposure_us


def _numbers_exposure_us(args):
    exposure_us = getattr(args, "numbers_exposure_us", None)
    if exposure_us is None:
        return DEFAULT_NUMBERS_EXPOSURE_US
    return exposure_us


def _format_range(start, count):
    if count <= 0:
        return None
    if count == 1:
        return str(start)
    return f"{start}..{start + count - 1}"


def _log_kernel_timing_summary(args, timing, prefix="[TIMING]"):
    slots = timing["entries_count"]
    leader_vsyncs = args.kernel_leader_frames
    payload_pad = (-512) % slots
    payload_vsyncs = (512 + payload_pad) // slots
    end_marker_vsyncs = 1 if args.kernel_blank_end_frame else 0
    cycle_vsyncs = leader_vsyncs + payload_vsyncs + end_marker_vsyncs
    leader_fires = leader_vsyncs * slots
    payload_fires = 512 + payload_pad
    end_marker_fires = end_marker_vsyncs * slots
    total_fires = leader_fires + payload_fires + end_marker_fires
    trig2_pulses = cycle_vsyncs if args.trig2_frame_zero else total_fires

    logger.info(
        f"{prefix} Kernel LUT: {slots} slots/VSYNC, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, effective VSYNC={timing['effective_frame_hz']:.3f}Hz, "
        f"bitplane rate={timing['effective_binary_rate_hz']:.1f}Hz."
    )
    cycle_period_ms = cycle_vsyncs * 1000.0 / timing["effective_frame_hz"]
    logger.info(
        f"{prefix} Kernel cycle: {cycle_vsyncs} VSYNC frames, {total_fires} bitplane fires, "
        f"{trig2_pulses} TRIG_OUT_2 pulses, period ~{cycle_period_ms:.1f}ms."
    )
    logger.info(
        f"{prefix} Cycle structure: {leader_vsyncs} leader marker VSYNCs "
        f"({leader_fires} bitplane fires), {payload_vsyncs} payload VSYNCs "
        f"(512 kernels + {payload_pad} pad blanks)"
        f"{', 1 end-marker VSYNC' if args.kernel_blank_end_frame else ''}."
    )
    logger.info(
        f"{prefix} DMD output polarity: "
        f"{'inverted after packing; black markers output white' if args.invert_dmd else 'normal'}."
    )
    if args.trig2_frame_zero:
        marker_level = "white" if args.invert_dmd else "black"
        logger.warning(
            f"{prefix} --trig2-frame-zero is active: TRIG_OUT_2 marks VSYNC frames, not individual kernels. "
            f"Each payload trigger covers up to {slots} kernels."
        )
        logger.info(
            f"{prefix} DAQ: ignore first {leader_vsyncs} TRIG_OUT_2 pulses "
            f"for the {marker_level} leader."
        )
    else:
        marker_level = "white" if args.invert_dmd else "black"
        logger.info(
            f"{prefix} Trigger map is relative to kernel-cycle start; "
            f"startup pulses emitted during DLPC arm or post-arm video-prime are outside this map."
        )
        logger.info(
            f"{prefix} DAQ: ignore first {leader_fires} TRIG_OUT_2 pulses "
            f"for the {marker_level} leader."
        )
        kernel_range = _format_range(leader_fires, 512)
        pad_range = _format_range(leader_fires + 512, payload_pad)
        end_range = _format_range(leader_fires + payload_fires, end_marker_fires)
        logger.info(f"{prefix} Trigger map: pulses {kernel_range} -> kernel_index = pulse - {leader_fires}.")
        if pad_range:
            logger.info(f"{prefix} Trigger map: pulses {pad_range} -> pad {marker_level}.")
        if end_range:
            logger.info(f"{prefix} Trigger map: pulses {end_range} -> end-marker {marker_level}.")


def _log_numbers_timing_summary(args, timing, prefix="[TIMING]"):
    exposure_us = _numbers_exposure_us(args)
    exposure_s = exposure_us / 1_000_000.0
    cycle_s = exposure_s * len(NUMBER_SEQUENCE)
    pulse_rate_hz = (
        timing["effective_frame_hz"]
        if args.trig2_frame_zero
        else timing["effective_binary_rate_hz"]
    )
    pulses_per_number = exposure_s * pulse_rate_hz
    trig2_mode = (
        "one pulse per VSYNC frame"
        if args.trig2_frame_zero
        else "one pulse per LUT bitplane"
    )
    logger.info(
        f"{prefix} Numbers mode: digits 1..9, exposure={exposure_us}us "
        f"({exposure_us / 1000.0:.3f}ms) per number, full cycle ~{cycle_s:.3f}s."
    )
    logger.info(
        f"{prefix} Numbers mode uses dynamic DisplayPort frames, not a custom packed LUT; "
        "existing Video Pattern Mode LUT timing remains unchanged."
    )
    logger.info(
        f"{prefix} TRIG_OUT_2 is the acquisition/index signal for numbers mode "
        f"({trig2_mode}); expect ~{pulses_per_number:.1f} pulses per displayed number. "
        "TRIG_OUT_1 is advisory only."
    )


def _log_calibration_square_summary(args, timing, prefix="[TIMING]"):
    pulse_rate_hz = (
        timing["effective_frame_hz"]
        if args.trig2_frame_zero
        else timing["effective_binary_rate_hz"]
    )
    trig2_mode = (
        "one pulse per VSYNC frame"
        if args.trig2_frame_zero
        else "one pulse per LUT bitplane"
    )
    logger.info(
        f"{prefix} Calibration square controls: W/A/S/D move, Q/E rotate, R/F resize, ESC or X exits. "
        "Use run_calibr_square.sh for terminal controls and pixel-bound feedback."
    )
    logger.info(
        f"{prefix} Calibration square uses dynamic DisplayPort frames, not a custom packed LUT; "
        "existing Video Pattern Mode LUT timing remains unchanged."
    )
    logger.info(
        f"{prefix} TRIG_OUT_2 is the acquisition/index signal for calibration square mode "
        f"({trig2_mode}, ~{pulse_rate_hz:.1f} pulses/s). It marks the running Video Pattern "
        "Mode sequence, not keyboard edits or square edges. TRIG_OUT_1 is advisory only."
    )


def _dry_run_timing(args):
    entries_count, exposure_us = _compute_kernel_lut_override(args, args.hz)
    entries, timing = build_lut_entries(
        _DryRunDLPC(),
        args.hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=exposure_us,
    )
    logger.info("[DRY RUN] Hardware was not opened. Timing uses target Hz, not measured DLPC900 timing.")
    logger.info(
        f"[DRY RUN] Pattern LUT: {len(entries)} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/"
        f"{timing['usable_frame_period_us']:.1f}us usable, idle headroom={timing['idle_headroom_us']:.1f}us."
    )
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 mode: {timing['trig2_mode']}; expected pulses/s="
        f"{timing['effective_frame_hz'] if args.trig2_frame_zero else timing['effective_binary_rate_hz']:.1f}."
    )
    if args.test == "kernel":
        _log_kernel_timing_summary(args, timing, prefix="[DRY RUN]")
    elif args.test == "numbers":
        _log_numbers_timing_summary(args, timing, prefix="[DRY RUN]")
    elif args.test == "calibr-square":
        _log_calibration_square_summary(args, timing, prefix="[DRY RUN]")
    if args.test != "kernel" and args.kernel_exposure_us is not None:
        logger.warning("[DRY RUN] --kernel-exposure-us is only used with --test kernel.")
    if args.test != "numbers" and args.numbers_exposure_us is not None:
        logger.warning("[DRY RUN] --numbers-exposure-us is only used with --test numbers.")


def _open_video_writer(path, target_hz):
    if cv2 is None:
        logger.warning("Cannot capture video, opencv-python is not installed.")
        return None
    logger.info(f"[+] Recording packed frames to {path}")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(path, fourcc, target_hz, (1920, 1080), isColor=True)


def _maybe_invert_frame(frame, invert_dmd):
    if not invert_dmd:
        return frame
    return frame ^ 0xFF


def _select_post_arm_prime_frame(initial_frame, dynamic_kind, kernel_frames, kernel_leader_frames):
    """Choose a frame that proves the post-arm DP video path is changing."""
    if dynamic_kind == "kernel" and kernel_frames is not None and len(kernel_frames) > 0:
        payload_index = min(max(0, kernel_leader_frames), len(kernel_frames) - 1)
        return kernel_frames[payload_index]
    return initial_frame


def _build_numbers_frames(engine):
    return tuple(
        engine.pack_patterns(
            engine.rgb_to_binary_patterns(
                generate_number_rgb(number, width=engine.width, height=engine.height)
            )
        )
        for number in NUMBER_SEQUENCE
    )


def _make_frame_provider(
    engine,
    initial_frame,
    dynamic_kind,
    args=None,
    kernel_frames=None,
    numbers_frames=None,
    calibration_square_state=None,
    invert_dmd=False,
):
    """Returns callable() -> frame. Hides per-mode frame regeneration from loop."""
    def _wrap(provider):
        if not invert_dmd:
            return provider
        def _provider_inverted():
            return _maybe_invert_frame(provider(), True)
        return _provider_inverted

    if dynamic_kind == "snake":
        return _wrap(engine.generate_snake_frame)
    if dynamic_kind == "clock":
        return _wrap(engine.generate_clock_frame)
    if dynamic_kind == "colors":
        from pattern_modes import _solid_color
        solid_r = engine.pack_patterns(engine.rgb_to_binary_patterns(_solid_color(0)))
        solid_g = engine.pack_patterns(engine.rgb_to_binary_patterns(_solid_color(1)))
        solid_b = engine.pack_patterns(engine.rgb_to_binary_patterns(_solid_color(2)))
        frames = (solid_r, solid_g, solid_b)
        def _provider():
            return frames[int(time.time() * 2) % 3]
        return _wrap(_provider)
    if dynamic_kind == "numbers":
        frames = numbers_frames
        if frames is None or len(frames) == 0:
            raise RuntimeError("No number frames generated for numbers mode.")
        exposure_s = _numbers_exposure_us(args) / 1_000_000.0
        state = {"start": None}

        # Numbers is a dynamic display-frame mode: each digit is a full packed
        # DisplayPort frame held by wall-clock time. The Video Pattern Mode LUT
        # remains the standard runtime LUT, so TRIG_OUT_2 continues to mark LUT
        # bitplanes/VSYNCs rather than digit boundaries.
        def _provider_numbers():
            now = time.monotonic()
            if state["start"] is None:
                state["start"] = now
            index = number_index_for_elapsed(now - state["start"], exposure_s, len(frames))
            return frames[index]
        return _wrap(_provider_numbers)
    if dynamic_kind == "calibr-square":
        # Calibration square is an interactive dynamic display-frame mode. The
        # square is re-packed only after keyboard edits; the DLPC900 LUT and
        # kernel timing paths are intentionally left unchanged.
        return _wrap(
            make_calibration_square_frame_provider(
                engine,
                initial_frame,
                control_file=getattr(args, "calibr_square_control_file", None),
                initial_state=calibration_square_state,
            )
        )
    if dynamic_kind == "kernel":
        frames = kernel_frames
        n = len(frames)
        black = engine.pack_patterns(engine.generate_solid(0))
        state = {"i": 0}
        if args is not None and args.kernel_single_shot:
            def _provider_once():
                i = state["i"]
                if i < n:
                    state["i"] = i + 1
                    return frames[i]
                return black
            return _wrap(_provider_once)
        def _provider_loop():
            f = frames[state["i"] % n]
            state["i"] += 1
            return f
        return _wrap(_provider_loop)
    return _wrap(lambda: initial_frame)


def main():
    args = _build_parser().parse_args()
    setup_logger(args.verbose)

    if args.hz not in (60, 120):
        logger.error(f"Unsupported Hz: {args.hz}. Only 60Hz and 120Hz are supported.")
        raise SystemExit(f"Unsupported Hz: {args.hz}")
    if args.seq_utilization <= 0.0 or args.seq_utilization > 1.0:
        logger.error("--seq-utilization must be in the interval (0, 1].")
        raise SystemExit("Invalid --seq-utilization value")
    if args.kernel_exposure_us is not None and args.kernel_exposure_us <= 0:
        logger.error("--kernel-exposure-us must be positive.")
        raise SystemExit("Invalid --kernel-exposure-us value")
    if args.numbers_exposure_us is not None and args.numbers_exposure_us <= 0:
        logger.error("--numbers-exposure-us must be positive.")
        raise SystemExit("Invalid --numbers-exposure-us value")
    if args.kernel_leader_frames < 0:
        logger.error("--kernel-leader-frames must be >= 0.")
        raise SystemExit("Invalid --kernel-leader-frames value")

    if args.dry_run_timing:
        _dry_run_timing(args)
        return

    target_hz = args.hz
    dmd_mapping = resolve_dmd_mapping(args.dmd, args.dmd_config) if args.dmd else None
    monitor_index = (
        args.monitor
        if args.monitor is not None
        else (
            dmd_mapping.glfw_monitor_index
            if dmd_mapping and dmd_mapping.glfw_monitor_index is not None
            else 0
        )
    )
    if dmd_mapping:
        if not dmd_mapping.xrandr_output:
            raise SystemExit(
                f"DMD {dmd_mapping.name} has no xrandr_output configured in dmd_devices.json. "
                "Refusing explicit --dmd hardware run until USB and DisplayPort mapping are both set."
            )
        logger.info(
            f"[+] DMD {dmd_mapping.name}: USB id_path={dmd_mapping.usb_id_path}, "
            f"expected devpath fragment={dmd_mapping.usb_devpath_contains or '<not required>'}, "
            f"xrandr_output={dmd_mapping.xrandr_output or '<not configured>'}, "
            f"GLFW monitor={monitor_index}"
        )
    dlpc = None
    engine = None
    try:
        import glfw
        from dlpc900_hid import DLPC900
        from pattern_engine import PatternEngine
        engine = PatternEngine(monitor_index=monitor_index, fps=target_hz)

        logger.info("[+] Initializing DLPC900...")
        dlpc = DLPC900(
            usb_id_path=dmd_mapping.usb_id_path if dmd_mapping else None,
            usb_devpath_contains=dmd_mapping.usb_devpath_contains if dmd_mapping else None,
        )

        if args.wake_dp:
            logger.info("[+] Waking up DisplayPort receiver...")
            dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        black_frame = engine.pack_patterns(engine.generate_solid(0))

        label, patterns, dynamic_kind = build_patterns(engine, args.test)
        logger.info(f"[+] Preparing Diagnostic Mode: {label}...")

        if args.trigger and patterns is None:
            logger.warning(f"Trigger mode does not support dynamic '{args.test}'; using checkerboard.")
            patterns = engine.generate_checkerboard()
            dynamic_kind = None
            label = "Static Checkerboard"

        lut_entries_count = None
        lut_per_entry_exposure_us = None
        if dynamic_kind == "kernel":
            lut_entries_count, lut_per_entry_exposure_us = _compute_kernel_lut_override(args, target_hz)
        if dynamic_kind == "kernel" and lut_per_entry_exposure_us is not None:
            logger.info(
                f"[+] Kernel exposure override: {lut_per_entry_exposure_us} us uniformly per kernel -> "
                f"{lut_entries_count} LUT entries per VSYNC (binary rate {lut_entries_count * target_hz} Hz)."
            )
        elif args.kernel_exposure_us is not None:
            logger.warning("--kernel-exposure-us is only used with --test kernel; ignoring it.")
        if dynamic_kind != "numbers" and args.numbers_exposure_us is not None:
            logger.warning("--numbers-exposure-us is only used with --test numbers; ignoring it.")

        kernel_frames = None
        numbers_frames = None
        calibration_square_state = None
        kernel_cycle_vsyncs = None
        kernel_blank_slot_count = 0
        kernel_cycle_kernels = None
        kernel_payload_vsyncs = None
        kernel_leader_fires = 0
        if dynamic_kind == "kernel":
            slots = lut_entries_count if lut_entries_count is not None else BITPLANES
            logger.info(
                f"[+] Prebuilding 512 kernel masks before sequencer arm "
                f"(kernel_px={args.kernel_px}, slots_per_vsync={slots}, "
                f"invert_dmd={args.invert_dmd}, "
                f"leader_frames={args.kernel_leader_frames}, "
                f"blank_end_frame={args.kernel_blank_end_frame})..."
            )
            kernel_masks = engine.generate_kernel_masks(args.kernel_px)
            kernel_payload_frames = engine.pack_kernel_frames(
                kernel_masks,
                slots_per_frame=slots,
                blank_end_frame=args.kernel_blank_end_frame,
            )
            kernel_payload_vsyncs = len(kernel_payload_frames)
            kernel_frames = [black_frame] * args.kernel_leader_frames + kernel_payload_frames
            kernel_cycle_vsyncs = len(kernel_frames)
            kernel_blank_slot_count = (slots - (512 % slots)) % slots
            kernel_leader_fires = args.kernel_leader_frames * slots
            kernel_cycle_kernels = 512 + kernel_blank_slot_count + (
                slots if args.kernel_blank_end_frame else 0
            )
            logger.info(
                f"[+] Kernel frames ready: {kernel_cycle_vsyncs} VSYNC frames per cycle "
                f"({args.kernel_leader_frames} leader + {kernel_payload_vsyncs} payload/end-marker) "
                f"covering {kernel_leader_fires + kernel_cycle_kernels} bitplane fires."
            )
        if dynamic_kind == "numbers":
            number_exposure_us = _numbers_exposure_us(args)
            logger.info(
                f"[+] Prebuilding {len(NUMBER_SEQUENCE)} number frames "
                f"(digits 1..9, exposure={number_exposure_us} us per number)..."
            )
            numbers_frames = _build_numbers_frames(engine)
            logger.info("[+] Number frames ready as full packed DisplayPort frames.")
        if dynamic_kind == "calibr-square":
            calibration_square_state = default_calibration_square_state(engine.width, engine.height)
            logger.info(
                "[+] Preparing calibration square: "
                f"{format_calibration_square_state(calibration_square_state, engine.width, engine.height)}."
            )
            logger.info("[+] Controls: W/A/S/D move, Q/E rotate, R/F resize, ESC exits.")
            if args.calibr_square_control_file:
                logger.info(f"[+] Reading calibration controls from {args.calibr_square_control_file}")

        if patterns is not None:
            frame = engine.pack_patterns(patterns)
        elif dynamic_kind == "snake":
            frame = engine.generate_snake_frame()
        elif dynamic_kind == "clock":
            frame = engine.generate_clock_frame()
        elif dynamic_kind == "kernel" and kernel_frames is not None:
            frame = kernel_frames[0]
        elif dynamic_kind == "numbers" and numbers_frames is not None:
            frame = numbers_frames[0]
        elif dynamic_kind == "calibr-square" and calibration_square_state is not None:
            frame = build_calibration_square_frame(engine, calibration_square_state)
        else:
            raise RuntimeError("No initial frame generated for the selected mode.")

        frame_provider = _make_frame_provider(
            engine,
            frame,
            dynamic_kind,
            args=args,
            kernel_frames=kernel_frames,
            numbers_frames=numbers_frames,
            calibration_square_state=calibration_square_state,
            invert_dmd=args.invert_dmd,
        )

        if args.trigger or dynamic_kind in ("kernel", "numbers", "calibr-square"):
            # Keep indexed dynamic playback deterministic: do not consume the
            # kernel/numbers/calibration provider during DLPC arm. The real
            # loop starts at frame 0 after configuration completes.
            prearm_frame_provider = lambda: _maybe_invert_frame(
                black_frame if args.trigger else frame, args.invert_dmd
            )
        else:
            prearm_frame_provider = frame_provider

        # Continuous background GL frame pump.
        # Why: a one-shot prime ("render N frames, then call start_pattern_display")
        # races against USB latency. By the time the DLPC900 receives the start
        # command, the DP buffer may be stale -> forced-swap (hw 0x08). Keep the
        # selected output stream live through the whole arm window.
        #
        # OpenGL contexts are thread-local. The main thread currently owns the GLFW context
        # (made current in PatternEngine.__init__). We hand it over to the pump thread for
        # the duration of DLPC configuration, then take it back before the render loop runs.
        pump_event = threading.Event()
        pump_thread_ready = threading.Event()

        def _continuous_pump():
            glfw.make_context_current(engine.window)
            pump_thread_ready.set()
            try:
                while pump_event.is_set():
                    engine.display_frame(prearm_frame_provider())
            finally:
                glfw.make_context_current(None)

        pump_thread = {"t": None}

        def _prime_video_buffer():
            logger.info("[+] Starting continuous background GL frame pump before sequencer arm...")
            # Release GL context from main thread so the pump thread can claim it.
            glfw.make_context_current(None)
            pump_event.set()
            pump_thread_ready.clear()
            t = threading.Thread(target=_continuous_pump, daemon=True)
            t.start()
            pump_thread["t"] = t
            # Wait for the pump thread to actually own the context and start pushing frames.
            pump_thread_ready.wait(timeout=1.0)
            # Give the pump a few VSYNCs of head-start so the DP buffer is fully primed
            # before the USB control thread starts issuing LUT writes + start command.
            time.sleep(0.1)

        def _frame_pump():
            # No-op: the background pump is already pushing frames continuously,
            # no synchronous pump is needed at this point.
            pass

        try:
            sequence_state = configure_dlpc900_for_video_pattern(
                dlpc, target_hz,
                dual_pixel=args.dual_pixel,
                sequence_utilization=args.seq_utilization,
                trig2_frame_zero=args.trig2_frame_zero,
                pre_arm_callback=_prime_video_buffer,
                frame_pump=_frame_pump,
                entries_count=lut_entries_count,
                per_entry_exposure_us=lut_per_entry_exposure_us,
            )
        finally:
            # Stop the background pump and reclaim the GL context for the main thread.
            if pump_event.is_set():
                logger.info("[+] Stopping continuous background GL frame pump.")
                pump_event.clear()
                if pump_thread["t"] is not None:
                    pump_thread["t"].join(timeout=1.0)
                glfw.make_context_current(engine.window)

        if args.trigger:
            post_arm_prime_frame = black_frame
            prime_label = "trigger-idle black frame"
        else:
            post_arm_prime_frame = _select_post_arm_prime_frame(
                frame,
                dynamic_kind,
                kernel_frames,
                args.kernel_leader_frames,
            )
            prime_label = (
                "first kernel payload frame"
                if dynamic_kind == "kernel" and post_arm_prime_frame is not frame
                else "number 1 frame"
                if dynamic_kind == "numbers"
                else "calibration square frame"
                if dynamic_kind == "calibr-square"
                else "initial pattern frame"
            )
        logger.info(f"[+] Priming DP output after sequencer arm with {prime_label}...")
        engine.display_frame(_maybe_invert_frame(post_arm_prime_frame, args.invert_dmd))
        if (
            dynamic_kind == "kernel"
            and kernel_frames is not None
            and len(kernel_frames) > 0
            and post_arm_prime_frame is not kernel_frames[0]
        ):
            logger.info("[+] Returning DP output to kernel leader frame before runtime cycle...")
            engine.display_frame(_maybe_invert_frame(kernel_frames[0], args.invert_dmd))

        if args.verbose >= 2:
            log_board_snapshot(dlpc, "POST-ARM-PRIME")
        if not verify_runtime_state(dlpc):
            raise RuntimeError(
                "Runtime state check failed after post-arm DP prime. "
                "Triggers are likely unavailable because mode 2/sequencer/lock is not valid."
            )

        logger.info(f"[+] Holding output for {args.runtime_seconds} seconds...")
        logger.info(f"[+] Starting Diagnostic Mode: {label}...")

        if dynamic_kind == "kernel":
            logger.info(
                f"[+] Kernel cycle: {kernel_cycle_vsyncs} VSYNC frames covering {kernel_cycle_kernels} "
                f"payload/end-marker bitplane fires plus {kernel_leader_fires} leader fires "
                f"({args.kernel_leader_frames} leader VSYNCs, 512 real kernels + {kernel_blank_slot_count} pad"
                f"{' + ' + str(sequence_state['timing']['entries_count']) + ' end-marker blanks' if args.kernel_blank_end_frame else ''}); "
                f"cycle period ~{kernel_cycle_vsyncs * 1000.0 / sequence_state['timing']['effective_frame_hz']:.1f} ms; "
                f"uniform exposure ~{sequence_state['timing']['exposure_us']} us per kernel; "
                f"DMD output polarity={'inverted' if args.invert_dmd else 'normal'}."
            )
            _log_kernel_timing_summary(args, sequence_state["timing"])
        elif dynamic_kind == "numbers":
            _log_numbers_timing_summary(args, sequence_state["timing"])
        elif dynamic_kind == "calibr-square":
            _log_calibration_square_summary(args, sequence_state["timing"])

        if args.trigger:
            logger.info("[+] Software Trigger Mode (Approach A) Active.")
            logger.info("    Press spacebar to trigger 1 frame of pattern sequence, or ESC to exit.")
            trig_frame = engine.pack_patterns(patterns)
            run_trigger_loop(
                engine,
                _maybe_invert_frame(black_frame, args.invert_dmd),
                _maybe_invert_frame(trig_frame, args.invert_dmd),
                args.runtime_seconds,
            )
            return
        video_writer = _open_video_writer(args.capture, target_hz) if args.capture else None
        try:
            run_render_loop(
                dlpc, engine, frame_provider, args, sequence_state,
                video_writer=video_writer, cv2_module=cv2,
            )
        finally:
            if video_writer is not None:
                video_writer.release()
                logger.info(f"[+] Video saved to {args.capture}")

    except Exception as exc:
        logger.exception(f"Runtime failed: {exc}")
    finally:
        logger.info("[+] Cleaning up...")
        if dlpc is not None:
            dlpc.start_pattern_display(0)
            dlpc.set_display_mode(0x00)
            dlpc.apply_block_lock_workaround()
        if engine is not None:
            engine.cleanup()


if __name__ == "__main__":
    main()
