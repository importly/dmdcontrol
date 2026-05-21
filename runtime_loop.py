"""Render loop with watchdog and auto-recover for DLPC900 Video Pattern Mode."""

import time

from dlpc_lifecycle import apply_pattern_sequence, ensure_video_pattern_mode
from logger import logger


def _format_hw(hw):
    return f"0x{hw:02X}" if hw is not None else "None"


def _maybe_recover_abort(dlpc, sequence_state, args, now_monotonic, last_abort_recover_at, hw, ms):
    auto_recover_abort = not args.no_auto_recover_abort
    has_abort = bool(hw & 0x40) if hw is not None else False
    seq_actually_stopped = not bool(ms.get("sequencer_running", True))
    if not (auto_recover_abort and has_abort and seq_actually_stopped):
        return last_abort_recover_at
    if (now_monotonic - last_abort_recover_at) < args.abort_recover_cooldown:
        return last_abort_recover_at

    logger.warning("[WATCHDOG] Sequencer abort bit detected; attempting automatic sequence re-arm.")
    try:
        dlpc.start_pattern_display(0)
        time.sleep(0.05)
        if not ensure_video_pattern_mode(dlpc, retries=2, poll_timeout_s=1.0):
            logger.warning("[WATCHDOG] Auto-recover failed to latch Video Pattern Mode before re-arm.")
        else:
            apply_pattern_sequence(dlpc, sequence_state["entries"])
            logger.warning("[WATCHDOG] Auto-recover sequence re-arm issued.")
    except Exception as recover_exc:
        logger.warning(f"[WATCHDOG] Auto-recover failed: {recover_exc}")
    return now_monotonic


def run_render_loop(dlpc, engine, frame_provider, args, sequence_state, video_writer=None, cv2_module=None):
    """Run the main render loop.

    frame_provider: callable() -> packed frame (np.ndarray).
    video_writer: optional cv2.VideoWriter (RGB->BGR conversion handled here).
    cv2_module: cv2 module reference (only needed if video_writer is not None).
    """
    end_t = time.time() + args.runtime_seconds
    if args.verbose >= 2:
        watchdog_interval_s = 1.0
    elif args.verbose >= 1:
        watchdog_interval_s = 2.0
    else:
        watchdog_interval_s = 0.0
    watchdog_last = time.monotonic()
    last_abort_recover_at = 0.0

    while time.time() < end_t and not engine.should_close():
        frame = frame_provider()
        engine.display_frame(frame)

        if watchdog_interval_s > 0.0:
            now_monotonic = time.monotonic()
            if (now_monotonic - watchdog_last) >= watchdog_interval_s:
                ms = dlpc.get_main_status() or {}
                mode, _ = dlpc.get_display_mode()
                hw = dlpc.get_hardware_status()
                logger.debug(
                    f"[WATCHDOG] mode={mode} seq={bool(ms.get('sequencer_running', False))} "
                    f"lock={bool(ms.get('external_source_locked', False))} hw={_format_hw(hw)}"
                )
                last_abort_recover_at = _maybe_recover_abort(
                    dlpc, sequence_state, args, now_monotonic, last_abort_recover_at, hw, ms
                )
                watchdog_last = now_monotonic

        if video_writer is not None:
            if cv2_module is None:
                raise RuntimeError("OpenCV capture path requested but cv2 is unavailable.")
            bgr_frame = cv2_module.cvtColor(frame, cv2_module.COLOR_RGB2BGR)
            video_writer.write(bgr_frame)


def run_trigger_loop(engine, black_frame, trig_frame, runtime_seconds):
    """Software trigger mode: spacebar toggles between black and pattern frame."""
    end_t = time.time() + runtime_seconds
    while time.time() < end_t and not engine.should_close():
        if engine.check_trigger_key():
            logger.info("[!] Triggering sequence...")
            engine.display_frame(trig_frame)
        else:
            engine.display_frame(black_frame)
