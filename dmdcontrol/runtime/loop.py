"""Render loop with watchdog and auto-recover for DLPC900 Video Pattern Mode."""

import time

from dmdcontrol.runtime.lifecycle import (
    apply_pattern_sequence,
    ensure_video_pattern_mode,
)
from dmdcontrol.support.logging import logger


def _format_bool_state(value, ok_when_true=True):
    state = bool(value)
    ok = state if ok_when_true else not state
    return f"{state}({'OK' if ok else 'WARN'})"


def _format_hw_details(hw, sequencer_running):
    if hw is None:
        return "hw=None(register read failed)"

    forced_swap = bool(hw & 0x08)
    seq_abort = bool(hw & 0x40)
    seq_error = bool(hw & 0x80)
    hard_fault = forced_swap or seq_error

    bits = []
    if hw & 0x01:
        bits.append("bit0 init_ok")
    if hw & 0x02:
        bits.append("bit1 dmd_compat_err")
    if hw & 0x04:
        bits.append("bit2 dmd_reset_err")
    if forced_swap:
        bits.append("bit3 forced_swap HARD_FAULT")
    if hw & 0x10:
        bits.append("bit4 set")
    if hw & 0x20:
        bits.append("bit5 reserved/common")
    if seq_abort:
        abort_meaning = "cosmetic while sequencer_running" if sequencer_running else "attention if sequencer stopped"
        bits.append(f"bit6 ABORT_latched {abort_meaning}")
    if seq_error:
        bits.append("bit7 SEQ_ERR HARD_FAULT")

    bit_text = "; ".join(bits) if bits else "no bits set"
    return f"hw=0x{hw:02X} hard_fault={hard_fault} bits=[{bit_text}]"


def _format_watchdog_status(mode, ms, hw):
    sequencer_running = bool(ms.get("sequencer_running", False))
    external_locked = bool(ms.get("external_source_locked", False))
    port1_sync_valid = bool(ms.get("port1_syncs_valid", False))
    video_frozen = bool(ms.get("video_frozen", False))
    dmd_parked = bool(ms.get("dmd_parked", False))
    mode_ok = mode == 2
    mode_description = {
        0: "Video Mode",
        1: "Pre-stored Pattern Mode",
        2: "Video Pattern Mode",
    }.get(mode, "unknown")

    return (
        f"[WATCHDOG] mode={mode}({mode_description}, {'OK' if mode_ok else 'WARN: expected Video Pattern Mode=2'}); "
        f"sequencer_running={_format_bool_state(sequencer_running)} required for triggers; "
        f"external_source_locked={_format_bool_state(external_locked)} advisory DP sync bit; "
        f"port1_syncs_valid={_format_bool_state(port1_sync_valid)} advisory P1 sync bit; "
        f"video_frozen={_format_bool_state(video_frozen, ok_when_true=False)}; "
        f"dmd_parked={_format_bool_state(dmd_parked, ok_when_true=False)}; "
        f"{_format_hw_details(hw, sequencer_running)}; "
        "hard-stop bits are forced_swap or SEQ_ERR, while ABORT/0x40 is cosmetic if the sequencer is still running."
    )


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
            logger.warning(
                "[WATCHDOG] Auto-recover failed to latch Video Pattern Mode before re-arm.")
        else:
            apply_pattern_sequence(dlpc, sequence_state["entries"])
            logger.warning("[WATCHDOG] Auto-recover sequence re-arm issued.")
    except Exception as recover_exc:
        logger.warning(f"[WATCHDOG] Auto-recover failed: {recover_exc}")
    return now_monotonic


def run_render_loop(
        dlpc,
        engine,
        frame_provider,
        args,
        sequence_state,
        video_writer=None,
        cv2_module=None):
    """Run the main render loop.

    frame_provider: callable() -> packed frame (np.ndarray).
    video_writer: optional cv2.VideoWriter (RGB->BGR conversion handled here).
    cv2_module: cv2 module reference (only needed if video_writer is not None).
    """
    end_t = None if args.runtime_seconds <= 0 else time.time() + args.runtime_seconds
    if args.verbose >= 2:
        watchdog_interval_s = 1.0
    elif args.verbose >= 1:
        watchdog_interval_s = 2.0
    else:
        watchdog_interval_s = 0.0
    watchdog_last = time.monotonic()
    last_abort_recover_at = 0.0

    while (end_t is None or time.time() < end_t) and not engine.should_close():
        frame = frame_provider()
        engine.display_frame(frame)

        if watchdog_interval_s > 0.0:
            now_monotonic = time.monotonic()
            if (now_monotonic - watchdog_last) >= watchdog_interval_s:
                ms = dlpc.get_main_status() or {}
                mode, _ = dlpc.get_display_mode()
                hw = dlpc.get_hardware_status()
                logger.debug(_format_watchdog_status(mode, ms, hw))
                last_abort_recover_at = _maybe_recover_abort(
                    dlpc,
                    sequence_state,
                    args,
                    now_monotonic,
                    last_abort_recover_at,
                    hw,
                    ms)
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
