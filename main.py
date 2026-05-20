import argparse
import threading
import time

import glfw

try:
    import cv2
except ImportError:
    cv2 = None

from config import BITPLANES, DEFAULT_SEQUENCE_UTILIZATION, SAFE_MARGIN_US
from dlpc900_hid import DLPC900
from dlpc_lifecycle import (
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
    parser.add_argument("--kernel-px", type=int, default=30,
                        help="Total kernel side length in pixels for --test kernel (must be a multiple of 3). "
                             "Default 30 (3x3 cells of 10px). Use 999 for naked-eye visibility (3x3 cells of 333px).")
    parser.add_argument("--kernel-single-shot", action="store_true",
                        help="Play the 22-frame kernel cycle once then hold black. Default: loop continuously.")
    parser.add_argument("--kernel-blank-end-frame", action="store_true",
                        help="Append one all-black VSYNC frame (24 black bitplanes) at the end of each kernel cycle "
                             "as a sync marker for downstream DAQ.")
    parser.add_argument("--kernel-exposure-us", type=int, default=None,
                        help="Per-kernel exposure time in microseconds (kernel mode only). "
                             "Default: use full 24-entry LUT (~694 us/kernel at 60 Hz, 1440 Hz binary). "
                             "Larger values reduce kernels per VSYNC and lengthen the 512-kernel cycle. "
                             "Ceiling = one VSYNC period (~16670 us at 60 Hz).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose diagnostic logging")
    return parser


def _open_video_writer(path, target_hz):
    if cv2 is None:
        logger.warning("Cannot capture video, opencv-python is not installed.")
        return None
    logger.info(f"[+] Recording packed frames to {path}")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(path, fourcc, target_hz, (1920, 1080), isColor=True)


def _make_frame_provider(engine, initial_frame, dynamic_kind, args=None, kernel_frames=None):
    """Returns callable() -> frame. Hides per-mode frame regeneration from loop."""
    if dynamic_kind == "snake":
        return engine.generate_snake_frame
    if dynamic_kind == "clock":
        return engine.generate_clock_frame
    if dynamic_kind == "colors":
        from pattern_modes import _solid_color
        solid_r = engine.pack_patterns(engine.rgb_to_binary_patterns(_solid_color(0)))
        solid_g = engine.pack_patterns(engine.rgb_to_binary_patterns(_solid_color(1)))
        solid_b = engine.pack_patterns(engine.rgb_to_binary_patterns(_solid_color(2)))
        frames = (solid_r, solid_g, solid_b)
        def _provider():
            return frames[int(time.time() * 2) % 3]
        return _provider
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
            return _provider_once
        def _provider_loop():
            f = frames[state["i"] % n]
            state["i"] += 1
            return f
        return _provider_loop
    return lambda: initial_frame


def main():
    args = _build_parser().parse_args()
    setup_logger(args.verbose)

    if args.hz not in (60, 120):
        logger.error(f"Unsupported Hz: {args.hz}. Only 60Hz and 120Hz are supported.")
        raise SystemExit(f"Unsupported Hz: {args.hz}")
    if args.seq_utilization <= 0.0 or args.seq_utilization > 1.0:
        logger.error("--seq-utilization must be in the interval (0, 1].")
        raise SystemExit("Invalid --seq-utilization value")

    target_hz = args.hz
    dlpc = None
    engine = None
    try:
        from pattern_engine import PatternEngine
        engine = PatternEngine(monitor_index=args.monitor, fps=target_hz)

        logger.info("[+] Initializing DLPC900...")
        dlpc = DLPC900()

        if args.wake_dp:
            logger.info("[+] Waking up DisplayPort receiver...")
            dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        black_frame = engine.pack_patterns(engine.generate_solid(0))

        # Continuous background GL frame pump.
        # Why: a one-shot prime ("render N black frames, then call start_pattern_display")
        # races against USB latency. By the time the DLPC900 actually receives the start
        # command (~15-30 ms after the pump loop ends), the DP buffer is stale -> forced-swap
        # error (hw 0x08) -> abort latch (hw 0x40). A background thread that keeps pushing
        # frames continuously means the buffer is fresh at the exact microsecond the
        # sequencer arms.
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
                    engine.display_frame(black_frame)
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

        lut_entries_count = None
        lut_per_entry_exposure_us = None
        if args.test == "kernel" and args.kernel_exposure_us is not None:
            frame_period_us = 1_000_000.0 / target_hz
            usable_us = (frame_period_us - SAFE_MARGIN_US) * args.seq_utilization
            n = int(usable_us // args.kernel_exposure_us)
            n = max(1, min(BITPLANES, n))
            lut_entries_count = n
            lut_per_entry_exposure_us = args.kernel_exposure_us
            logger.info(
                f"[+] Kernel exposure override: {args.kernel_exposure_us} us per kernel -> "
                f"{n} LUT entries per VSYNC (binary rate {n * target_hz} Hz)."
            )

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

        log_board_snapshot(dlpc, "POST-CONFIG")
        logger.info(f"[+] Holding output for {args.runtime_seconds} seconds...")

        label, patterns, dynamic_kind = build_patterns(engine, args.test)
        logger.info(f"[+] Starting Diagnostic Mode: {label}...")

        kernel_frames = None
        if dynamic_kind == "kernel":
            slots = sequence_state["timing"]["entries_count"]
            logger.info(
                f"[+] Building 512 kernel masks (kernel_px={args.kernel_px}, "
                f"slots_per_vsync={slots}, blank_end_frame={args.kernel_blank_end_frame})..."
            )
            kernel_masks = engine.generate_kernel_masks(args.kernel_px)
            kernel_frames = engine.pack_kernel_frames(
                kernel_masks,
                slots_per_frame=slots,
                blank_end_frame=args.kernel_blank_end_frame,
            )
            cycle_vsyncs = len(kernel_frames)
            blank_slot_count = (slots - (512 % slots)) % slots
            cycle_kernels = 512 + blank_slot_count + (slots if args.kernel_blank_end_frame else 0)
            logger.info(
                f"[+] {cycle_vsyncs} VSYNC frames per cycle covering {cycle_kernels} bitplane fires "
                f"(512 real kernels + {blank_slot_count} pad"
                f"{' + ' + str(slots) + ' end-marker blanks' if args.kernel_blank_end_frame else ''}); "
                f"cycle period ~{cycle_vsyncs * 1000.0 / target_hz:.1f} ms; "
                f"per-kernel exposure ~{sequence_state['timing']['exposure_us']} us."
            )

        if args.trigger:
            logger.info("[+] Software Trigger Mode (Approach A) Active.")
            logger.info("    Press spacebar to trigger 1 frame of pattern sequence, or ESC to exit.")
            if patterns is None:
                logger.warning(f"Trigger mode does not support dynamic '{args.test}'; using checkerboard.")
                patterns = engine.generate_checkerboard()
            trig_frame = engine.pack_patterns(patterns)
            run_trigger_loop(engine, black_frame, trig_frame, args.runtime_seconds)
            return

        if patterns is not None:
            frame = engine.pack_patterns(patterns)
        elif dynamic_kind == "snake":
            frame = engine.generate_snake_frame()
        elif dynamic_kind == "clock":
            frame = engine.generate_clock_frame()
        elif dynamic_kind == "kernel":
            frame = kernel_frames[0]
        else:
            raise RuntimeError("No initial frame generated for the selected mode.")

        engine.display_frame(frame)
        time.sleep(1.0)
        log_board_snapshot(dlpc, "POST-PATTERN-FRAME (after first pattern rendered)")
        if not verify_runtime_state(dlpc):
            raise RuntimeError(
                "Runtime state check failed after first frame. "
                "Triggers are likely unavailable because mode 2/sequencer/lock is not valid."
            )

        frame_provider = _make_frame_provider(
            engine, frame, dynamic_kind, args=args, kernel_frames=kernel_frames
        )
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
