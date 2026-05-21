import argparse
import threading
import time

try:
    import cv2
except ImportError:
    cv2 = None

from config import BITPLANES, DEFAULT_SEQUENCE_UTILIZATION, SAFE_MARGIN_US
from dlpc_lifecycle import (
    build_lut_entries,
    configure_dlpc900_for_video_pattern,
    log_board_snapshot,
    verify_runtime_state,
)
from logger import logger, setup_logger
from pattern_modes import PATTERN_NAMES, build_patterns
from runtime_loop import run_render_loop, run_trigger_loop


def _build_parser():
    parser = argparse.ArgumentParser(description="DLPC900 1080p Video Pattern Runtime")
    parser.add_argument("--hz", type=int, default=60, help="Target Hz (60 or 120, experimental)")
    parser.add_argument("--monitor", type=int, default=0, help="GLFW monitor index")
    parser.add_argument("--test", choices=PATTERN_NAMES, default="checkerboard",
                        help=f"Diagnostic pattern mode. Choices: {', '.join(PATTERN_NAMES)}.")
    parser.add_argument("--trigger", action="store_true", help="Software Trigger Mode (Approach A)")
    parser.add_argument("--runtime-seconds", type=int, default=60, help="Runtime for diagnostic patterns")
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
            f"{marker_level} marker pulses emitted during DLPC arm are outside this map."
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
    elif args.kernel_exposure_us is not None:
        logger.warning("[DRY RUN] --kernel-exposure-us is only used with --test kernel.")


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


def _make_frame_provider(engine, initial_frame, dynamic_kind, args=None, kernel_frames=None, invert_dmd=False):
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
    if args.kernel_leader_frames < 0:
        logger.error("--kernel-leader-frames must be >= 0.")
        raise SystemExit("Invalid --kernel-leader-frames value")

    if args.dry_run_timing:
        _dry_run_timing(args)
        return

    target_hz = args.hz
    dlpc = None
    engine = None
    try:
        import glfw
        from dlpc900_hid import DLPC900
        from pattern_engine import PatternEngine
        engine = PatternEngine(monitor_index=args.monitor, fps=target_hz)

        logger.info("[+] Initializing DLPC900...")
        dlpc = DLPC900()

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

        kernel_frames = None
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

        if patterns is not None:
            frame = engine.pack_patterns(patterns)
        elif dynamic_kind == "snake":
            frame = engine.generate_snake_frame()
        elif dynamic_kind == "clock":
            frame = engine.generate_clock_frame()
        elif dynamic_kind == "kernel" and kernel_frames is not None:
            frame = kernel_frames[0]
        else:
            raise RuntimeError("No initial frame generated for the selected mode.")

        frame_provider = _make_frame_provider(
            engine, frame, dynamic_kind, args=args, kernel_frames=kernel_frames, invert_dmd=args.invert_dmd
        )

        if args.trigger or dynamic_kind == "kernel":
            # Keep kernel playback indexing deterministic: do not consume the
            # kernel frame provider during DLPC arm. The real loop starts at
            # kernel frame 0 after configuration completes.
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
            if args.verbose >= 2:
                log_board_snapshot(dlpc, "POST-CONFIG")
            if not verify_runtime_state(dlpc):
                raise RuntimeError(
                    "Runtime state check failed after sequencer arm. "
                    "Triggers are likely unavailable because mode 2/sequencer/lock is not valid."
                )
        finally:
            # Stop the background pump and reclaim the GL context for the main thread.
            if pump_event.is_set():
                logger.info("[+] Stopping continuous background GL frame pump.")
                pump_event.clear()
                if pump_thread["t"] is not None:
                    pump_thread["t"].join(timeout=1.0)
                glfw.make_context_current(engine.window)

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
