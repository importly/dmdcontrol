import argparse
import time

try:
    import cv2
except ImportError:
    cv2 = None

from config import DEFAULT_SEQUENCE_UTILIZATION
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
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose diagnostic logging")
    return parser


def _open_video_writer(path, target_hz):
    if cv2 is None:
        logger.warning("Cannot capture video, opencv-python is not installed.")
        return None
    logger.info(f"[+] Recording packed frames to {path}")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    return cv2.VideoWriter(path, fourcc, target_hz, (1920, 1080), isColor=True)


def _make_frame_provider(engine, initial_frame, dynamic_kind):
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

        def _prime_video_buffer():
            logger.info("[+] Priming DLPC900 video buffer with live GL frames before sequencer arm...")
            for _ in range(12):
                engine.display_frame(black_frame)

        def _frame_pump():
            for _ in range(3):
                engine.display_frame(black_frame)

        sequence_state = configure_dlpc900_for_video_pattern(
            dlpc, target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
            pre_arm_callback=_prime_video_buffer,
            frame_pump=_frame_pump,
        )

        log_board_snapshot(dlpc, "POST-CONFIG")
        logger.info(f"[+] Holding output for {args.runtime_seconds} seconds...")

        label, patterns, dynamic_kind = build_patterns(engine, args.test)
        logger.info(f"[+] Starting Diagnostic Mode: {label}...")

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

        frame_provider = _make_frame_provider(engine, frame, dynamic_kind)
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
