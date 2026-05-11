import argparse
import time

try:
    import cv2
except ImportError:
    cv2 = None

from dlpc900_hid import DLPC900
from logger import setup_logger, logger


def generate_solid_color(color_idx, width=1920, height=1080):
    import numpy as np

    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, color_idx] = 255
    return img


TARGET_HZ = 60
BITPLANES = 24
MIN_EXPOSURE_US = 150
INTER_PATTERN_DARK_US = 0
MAX_BINARY_RATE_HZ_DLP6500 = 9523
SAFE_MARGIN_US = 250.0
MAX_MEASURED_VSYNC_DEVIATION_RATIO = 0.25
DEFAULT_SEQUENCE_UTILIZATION = 0.90


def log_board_snapshot(dlpc, tag):
    logger.debug("=" * 66)
    logger.debug(f"  DLPC900 Status Snapshot: {tag}")
    logger.debug("=" * 66)

    hw = dlpc.get_hardware_status()
    if hw is not None:
        logger.debug(f"Hardware Status raw: 0x{hw:02X}")
        logger.debug(f"  Internal init successful: {bool(hw & 0x01)}")
        logger.debug(f"  DMD compatibility error: {bool(hw & 0x02)}")
        logger.debug(f"  DMD reset ctrl error:    {bool(hw & 0x04)}")
        logger.debug(f"  Forced swap error:       {bool(hw & 0x08)}")
        logger.debug(f"  Sequence abort flag:     {bool(hw & 0x40)}")
        logger.debug(f"  Sequence error flag:     {bool(hw & 0x80)}")

    ms = dlpc.get_main_status()
    if ms:
        logger.debug(f"Main Status raw:      {ms['raw']}")
        logger.debug(f"  DMD parked:         {ms['dmd_parked']}")
        logger.debug(f"  Sequencer running:  {ms['sequencer_running']}")
        logger.debug(f"  Video frozen:       {ms['video_frozen']}")
        logger.debug(f"  External src lock:  {ms['external_source_locked']}")
        logger.debug(f"  Port1 sync valid:   {ms['port1_syncs_valid']}")
        logger.debug(f"  Port2 sync valid:   {ms['port2_syncs_valid']}")

    pc = dlpc.get_port_config()
    if pc:
        logger.debug(f"Port Config raw:      {pc['raw']}")
        logger.debug(f"  Pixel mode:         {pc['pixel_mode']}")
        logger.debug(f"  Pixel clock:        {pc['pixel_clock']}")
        logger.debug(f"  Data enable:        {pc['data_enable']}")
        logger.debug(f"  Sync select:        {pc['sync_select']}")

    dd = dlpc.get_display_dimensions()
    if dd:
        logger.debug("Display Dimensions:")
        logger.debug(
            f"  Total:              {dd['total_pixels_per_line']} x {dd['total_lines_per_frame']}"
        )
        logger.debug(
            f"  Active:             {dd['active_pixels_per_line']} x {dd['active_lines_per_frame']}"
        )
        logger.debug(
            f"  First pixel:        ({dd['first_active_pixel']}, {dd['first_active_line']})"
        )
        logger.debug(f"  Pixel clock:        {dd['pixel_clock_khz']} kHz")

    err = dlpc.get_last_error()
    if err is not None:
        logger.debug(f"Last Error:           {err}")

    mode, err_flag = dlpc.get_display_mode()
    if mode is not None:
        logger.debug(f"Display Mode:         {mode} (error flag: {err_flag})")

    logger.debug("=" * 66)


def build_lut_entries(
    dlpc,
    target_hz,
    sequence_utilization=DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero=False,):
    if target_hz <= 0:
        raise ValueError("target_hz must be positive")
    if sequence_utilization <= 0.0 or sequence_utilization > 1.0:
        raise ValueError("sequence_utilization must be in the interval (0, 1].")

    measured_frame_hz = None
    dd = dlpc.get_display_dimensions()
    if (
        dd
        and dd.get("pixel_clock_khz")
        and dd.get("total_pixels_per_line")
        and dd.get("total_lines_per_frame")
    ):
        total_pixels = int(dd["total_pixels_per_line"]) * int(dd["total_lines_per_frame"])
        pixel_clock_hz = int(dd["pixel_clock_khz"]) * 1000
        if total_pixels > 0 and pixel_clock_hz > 0:
            measured_frame_hz = pixel_clock_hz / total_pixels

    if measured_frame_hz is not None:
        rel_err = abs(measured_frame_hz - float(target_hz)) / float(target_hz)
        if rel_err > MAX_MEASURED_VSYNC_DEVIATION_RATIO:
            logger.warning(
                "[WARNING] Ignoring unstable measured VSYNC %.3f Hz (target %.3f Hz, deviation %.1f%%). "
                "Using target Hz for LUT timing. Display dims at measurement: total=%sx%s, active=%sx%s, pclk=%skHz",
                measured_frame_hz,
                float(target_hz),
                rel_err * 100.0,
                dd.get("total_pixels_per_line") if dd else "?",
                dd.get("total_lines_per_frame") if dd else "?",
                dd.get("active_pixels_per_line") if dd else "?",
                dd.get("active_lines_per_frame") if dd else "?",
                dd.get("pixel_clock_khz") if dd else "?",
            )
            measured_frame_hz = None

    effective_frame_hz = measured_frame_hz if measured_frame_hz else float(target_hz)
    timing_source = "measured" if measured_frame_hz else "target_fallback"
    frame_period_us = 1_000_000.0 / effective_frame_hz
    safe_frame_period_us = frame_period_us - SAFE_MARGIN_US
    if safe_frame_period_us <= 0:
        raise ValueError(
            f"Frame period {frame_period_us:.2f} us is not larger than safety margin {SAFE_MARGIN_US:.2f} us."
        )

    requested_binary_rate_hz = float(target_hz) * BITPLANES
    if requested_binary_rate_hz > MAX_BINARY_RATE_HZ_DLP6500:
        raise ValueError(
            f"Requested binary rate {requested_binary_rate_hz:.1f} Hz exceeds "
            f"DLP6500 1-bit limit (~{MAX_BINARY_RATE_HZ_DLP6500} Hz)."
        )

    effective_binary_rate_hz = effective_frame_hz * BITPLANES
    if effective_binary_rate_hz > MAX_BINARY_RATE_HZ_DLP6500:
        raise ValueError(
            f"Measured source binary rate {effective_binary_rate_hz:.1f} Hz exceeds "
            f"DLP6500 1-bit limit (~{MAX_BINARY_RATE_HZ_DLP6500} Hz)."
        )

    min_segment_us = MIN_EXPOSURE_US + INTER_PATTERN_DARK_US
    usable_frame_period_us = safe_frame_period_us * sequence_utilization
    segment_budget_us = usable_frame_period_us / BITPLANES
    if segment_budget_us < min_segment_us:
        max_safe_hz = 1_000_000.0 / ((BITPLANES * min_segment_us / sequence_utilization) + SAFE_MARGIN_US)
        raise ValueError(
            f"Requested sequence exceeds VSYNC budget: each pattern has {segment_budget_us:.2f} us "
            f"but needs >= {min_segment_us} us (exposure {MIN_EXPOSURE_US} us + dark {INTER_PATTERN_DARK_US} us). "
            f"Reduce source frame rate to <= {max_safe_hz:.2f} Hz."
        )

    # Keep explicit margin so sequence completion is strictly earlier than the next VSYNC.
    segment_us = int(usable_frame_period_us / BITPLANES)
    exposure_us = segment_us - INTER_PATTERN_DARK_US
    if exposure_us < MIN_EXPOSURE_US:
        max_safe_hz = 1_000_000.0 / ((BITPLANES * min_segment_us / sequence_utilization) + SAFE_MARGIN_US)
        raise ValueError(
            f"Computed exposure {exposure_us} us is below minimum {MIN_EXPOSURE_US} us. "
            f"Reduce source frame rate to <= {max_safe_hz:.2f} Hz."
        )

    total_sequence_us = (exposure_us + INTER_PATTERN_DARK_US) * BITPLANES
    idle_headroom_us = frame_period_us - total_sequence_us

    entries = []
    for bit_pos in range(BITPLANES):
        clear_flag = bit_pos == (BITPLANES - 1)
        trig2_disable = (bit_pos != 0) if trig2_frame_zero else False
        entries.append(
            (
                bit_pos,
                exposure_us,
                clear_flag,
                1,
                7,
                INTER_PATTERN_DARK_US,
                trig2_disable,
                bit_pos,
            )
        )

    timing = {
        "timing_source": timing_source,
        "sequence_utilization": sequence_utilization,
        "trig2_mode": "frame_zero" if trig2_frame_zero else "per_bitplane",
        "frame_period_us": frame_period_us,
        "safe_frame_period_us": safe_frame_period_us,
        "usable_frame_period_us": usable_frame_period_us,
        "safe_margin_us": SAFE_MARGIN_US,
        "measured_frame_hz": measured_frame_hz,
        "effective_frame_hz": effective_frame_hz,
        "requested_binary_rate_hz": requested_binary_rate_hz,
        "effective_binary_rate_hz": effective_binary_rate_hz,
        "exposure_us": exposure_us,
        "dark_us": INTER_PATTERN_DARK_US,
        "total_sequence_us": total_sequence_us,
        "idle_headroom_us": idle_headroom_us,
    }
    return entries, timing


def wait_for_external_lock(dlpc, timeout_s=4.0):
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("external_source_locked"):
            return True
        time.sleep(0.2)
    return False


def wait_for_sequencer_running(dlpc, timeout_s=1.5):
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("sequencer_running"):
            return True
        time.sleep(0.1)
    return False


def ensure_video_pattern_mode(dlpc, retries=3, poll_timeout_s=1.2):
    mode, _ = dlpc.get_display_mode()
    if mode == 2:
        return True

    for attempt in range(1, retries + 1):
        logger.warning(
            f"[WARNING] Mode readback shows {mode}, not 2! Retrying mode transition ({attempt}/{retries})..."
        )
        dlpc.set_display_mode(0x02)

        # Give the DLPC900 time to complete internal mode reallocation, then poll briefly.
        time.sleep(0.35)
        deadline = time.time() + poll_timeout_s
        while time.time() < deadline:
            mode, _ = dlpc.get_display_mode()
            if mode == 2:
                logger.debug(f"  - After retry {attempt}, mode readback: {mode}")
                return True
            time.sleep(0.1)

        logger.debug(f"  - After retry {attempt}, mode readback: {mode}")

    return False


def apply_pattern_sequence(dlpc, entries):
    order = [int(entry[0]) for entry in entries]
    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(len(entries), repeat=True)
    dlpc.set_pattern_lut_reorder(order, repeat=True)
    dlpc.start_pattern_display(2)
    time.sleep(0.2)

    # Immediately check for abort latch: if start_pattern_display(2) fired during a
    # mid-frame GPU commit, hw bit 0x40 is set. Detect it here, clear it, and retry once
    # rather than silently entering the main loop with broken triggers.
    hw = dlpc.get_hardware_status()
    if hw is not None and (hw & 0x40):
        logger.warning(
            f"[WARN] Abort latch (hw=0x{hw:02X}) set immediately after sequencer start. "
            "Clearing and retrying: stop → park/unpark → resend LUT → restart."
        )
        dlpc.start_pattern_display(0)
        time.sleep(0.1)
        dlpc.apply_block_lock_workaround()
        time.sleep(1.0)
        # Resend full LUT config — required after park/unpark per DLPU018J
        dlpc.set_pattern_lut_definition(entries)
        dlpc.set_pattern_lut_config(len(entries), repeat=True)
        dlpc.set_pattern_lut_reorder(order, repeat=True)
        dlpc.start_pattern_display(2)
        time.sleep(0.2)
        hw2 = dlpc.get_hardware_status()
        if hw2 is not None and (hw2 & 0x40):
            logger.error(
                f"[ERROR] Abort latch still set (hw=0x{hw2:02X}) after retry. "
                "Triggers will be unreliable. Consider power cycling the DLPC900."
            )
        else:
            hw2_str = f"0x{hw2:02X}" if hw2 is not None else "??"
            logger.info(f"[+] Abort latch cleared after retry (hw={hw2_str}). Sequencer restarted.")


def configure_dlpc900_for_video_pattern(
    dlpc,
    target_hz=60,
    dual_pixel=False,
    sequence_utilization=DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero=False,
):
    logger.info(
        f"[+] Configuring DLPC900 for 1920x1080 @ {target_hz}Hz Video Pattern Mode ({BITPLANES} bit-planes)..."
    )
    logger.debug("Following TI documentation sequence (DLPU018J Section 5.1)...")

    # Step 1: Stop any existing pattern playback
    dlpc.start_pattern_display(0)
    time.sleep(0.2)

    # Step 2: Configure LEDs
    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    # Step 3: Enter Video Mode (0) FIRST with DisplayPort source
    # Per DLPU018J p.56: "Must first change to Video Mode (0) with desired source enabled"
    logger.debug("  - Entering Video Mode (0) with DisplayPort source...")
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)  # DisplayPort TODO! try hdmi
    dlpc.toggle_dual_pixel_mode(bool(dual_pixel))
    logger.info(
        f"[+] Parallel input pixel mode: {'Dual P1-P2' if dual_pixel else 'Single P1'}"
    )
    
    # CRITICAL FIX: Explicitly tell the DLPC900 to use the full 1920x1080 active area.
    # Otherwise, it might remember a previous 512x512 crop from Flash and truncate patterns!
    logger.debug("  - Forcing Input Display Resolution to 1920x1080...")
    dlpc.set_input_display_resolution(0, 0, 1920, 1080)

    dlpc.apply_block_lock_workaround()

    # Step 4: Wait for sync lock (REQUIRED before mode 2 transition)
    logger.info("[+] Waiting for external source sync lock...")
    if wait_for_external_lock(dlpc, timeout_s=4.0):
        logger.info("[+] External source lock acquired. Dwelling in Mode 0 for video buffer stabilization (3s)...")
        # "external_source_locked" means VSYNC edges detected, not that the video buffer
        # content is consistent. Dwelling here lets the DLPC900 fill its internal buffer
        # with valid frames before we arm the sequencer. Without this, the first
        # start_pattern_display(2) collides with a mid-frame GPU commit (forced-swap 0x08)
        # which permanently latches the abort flag (0x40).
        time.sleep(3.0)
        logger.info("[+] Mode 0 buffer dwell complete. Ready for Video Pattern Mode.")
    else:
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "External source sync lock was not acquired. "
            f"Main status: {ms}. Without lock, Video Pattern Mode and trigger outputs are unreliable."
        )

    # Step 5: Set display mode to Video Pattern Mode (0x02)
    # Per DLPU018J p.56: "Takes approximately 300ms to complete the transition"
    logger.debug("  - Switching to Video Pattern Mode (0x02)...")
    dlpc.set_display_mode(0x02)

    # CRITICAL: Wait 300ms for mode transition as per documentation
    logger.debug("  - Waiting 300ms for mode transition (per TI spec)...")
    time.sleep(0.3)

    # Explicitly stop before park: DLPU018J requires stop before park in Video Pattern Mode.
    # Without this, the firmware latches the abort flag (hw bit 0x40) during park even when
    # no sequence was running, because it sees a park without a preceding stop command.
    dlpc.start_pattern_display(0)
    time.sleep(0.05)
    dlpc.apply_block_lock_workaround()

    # Additional settling time
    time.sleep(0.1)

    # Step 6: Verify we're actually in mode 2
    mode, _ = dlpc.get_display_mode()
    logger.debug(f"  - Display mode readback: {mode} (expected: 2)")

    if not ensure_video_pattern_mode(dlpc, retries=3, poll_timeout_s=1.5):
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "Failed to enter Video Pattern Mode (mode 2) after retries. "
            f"Mode readback: {mode}, main status: {ms}. Trigger outputs are disabled in Video Mode."
        )

    # Secure the Global Hardware Trigger configs (DLPU018J Table 2-118/2-120)
    # Byte 0 Bit 0 = polarity (0=non-inverted). There is NO enable bit in the spec.
    # Non-inverted constraint: rising_delay <= falling_delay. Min pulse width: 20µs.
    dlpc.configure_trigger_out_1(polarity_high=True, rising_delay_us=5, falling_delay_us=20)
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_1 config sent. Last error: {err}")
    
    dlpc.configure_trigger_out_2(polarity_high=True, rising_delay_us=0, falling_delay_us=20)
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_2 config sent. Last error: {err}")
    
    # Read back trigger configs to verify hardware accepted them
    t1 = dlpc.get_trigger_out_1()
    t2 = dlpc.get_trigger_out_2()
    logger.info(f"  - TRIG_OUT_1 readback: {t1}")
    logger.info(f"  - TRIG_OUT_2 readback: {t2}")

    # Step 7: Define pattern LUT (bit-plane extraction)
    entries, timing = build_lut_entries(
        dlpc,
        target_hz,
        sequence_utilization=sequence_utilization,
        trig2_frame_zero=trig2_frame_zero,
    )
    logger.info(
        f"[TIMING] LUT timing source: {timing['timing_source']} (effective VSYNC {timing['effective_frame_hz']:.3f} Hz)."
    )
    if timing["measured_frame_hz"] and abs(timing["measured_frame_hz"] - target_hz) > 0.5:
        logger.warning(
            f"[WARNING] Source VSYNC is {timing['measured_frame_hz']:.3f} Hz while --hz is {target_hz} Hz. "
            f"Sequencer timing follows source VSYNC ({timing['effective_frame_hz']:.3f} Hz)."
        )
    logger.info(
        f"[+] LUT: {BITPLANES} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/{timing['usable_frame_period_us']:.1f}us "
        f"(utilization {timing['sequence_utilization']:.2f}, reserved margin {timing['safe_margin_us']:.1f}us, "
        f"idle headroom {timing['idle_headroom_us']:.1f}us from {timing['frame_period_us']:.1f}us VSYNC), "
        f"binary rate req={timing['requested_binary_rate_hz']:.1f}Hz, "
        f"effective={timing['effective_binary_rate_hz']:.1f}Hz"
    )
    if timing["trig2_mode"] == "frame_zero":
        logger.info(
            "[SCOPE] Expected TRIG_OUT_2: ~20us pulse width, triggered only on bitplane 0."
        )
        logger.info(
            f"[SCOPE] TRIG_OUT_2 mode: frame_zero anchor (~{timing['effective_frame_hz']:.3f} pulses/s)."
        )
    else:
        logger.info(
            "[SCOPE] Expected TRIG_OUT_2: ~20us pulse width, active at each bitplane start."
        )
        logger.info(
            f"[SCOPE] TRIG_OUT_2 mode: per_bitplane (~{timing['effective_binary_rate_hz']:.1f} pulses/s)."
        )
    logger.info(
        f"[SCOPE] Expected TRIG_OUT_1: ~{timing['effective_frame_hz']:.3f} pulses/s. "
        "With dark=0us, pulse may appear as a wide frame-level gate."
    )
    # Wait for VSYNC buffer stabilization before arming the sequencer.
    # The 300ms mode-transition spec covers the mode change itself, not the video
    # buffer sync. Empirically, if start_pattern_display(2) fires before the DLPC900
    # has processed several VSYNC cycles in mode 2, the first frame collision causes
    # a forced-swap (hw 0x08) which latches the abort flag (0x40). Waiting ~2s lets
    # the DLPC900 fully lock onto the GPU's VSYNC before the sequencer arms.
    logger.debug("  - Final VSYNC settling wait (1s)...")
    time.sleep(1.0)
    logger.info(f"[+] Applying LUT reorder with {len(entries)} entries...")
    apply_pattern_sequence(dlpc, entries)

    # Step 8: Sequencer start command was issued in apply_pattern_sequence().
    logger.info("[+] Pattern sequencer start command issued.")

    # Verify mode remained latched after start command.
    if not ensure_video_pattern_mode(dlpc, retries=2, poll_timeout_s=1.0):
        mode, _ = dlpc.get_display_mode()
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "Mode dropped out of Video Pattern Mode after sequencer start. "
            f"Mode readback: {mode}, main status: {ms}."
        )

    if not wait_for_sequencer_running(dlpc, timeout_s=1.5):
        ms = dlpc.get_main_status() or {}
        hw = dlpc.get_hardware_status()
        raise RuntimeError(
            "Pattern sequencer did not report running after start command. "
            f"Main status: {ms}, hardware status: {hw}."
        )

    hw = dlpc.get_hardware_status()
    if hw is not None and (hw & 0xC0):
        logger.warning(
            f"[WARNING] Hardware status indicates sequencer abort/error bits set (0x{hw:02X}). "
            "These bits can be latched from prior faults; monitor runtime watchdog for live state changes."
        )

    return {
        "entries": entries,
        "timing": timing,
    }


def verify_runtime_state(dlpc):
    ms = dlpc.get_main_status() or {}
    mode, _ = dlpc.get_display_mode()
    hw = dlpc.get_hardware_status()

    seq_abort = bool(hw & 0x40) if hw is not None else False
    seq_error = bool(hw & 0x80) if hw is not None else False

    checks = {
        "display_mode_is_video_pattern": mode == 2,
        "sequencer_running": bool(ms.get("sequencer_running", False)),
        "external_source_locked": bool(ms.get("external_source_locked", False)),
    }

    logger.debug("Verification:")
    for name, ok in checks.items():
        logger.debug(f"  {name:30} {'PASS' if ok else 'FAIL'}")

    all_ok = all(checks.values())
    if not all_ok:
        logger.warning("[WARNING] Runtime verification checks failed!")
        logger.warning(
            "           Video Pattern Mode (2), source lock, or sequencer health check failed."
        )
        logger.warning(
            "           Check DisplayPort sync lock and mode transition timing."
        )
        if hw is not None:
            logger.warning(f"           Hardware status raw: 0x{hw:02X}")
    else:
        if seq_abort or seq_error:
            logger.warning(
                f"[WARNING] Runtime health bits indicate abort/error flags are set (0x{hw:02X}) despite mode/sequencer lock. "
                "Treat as sticky/historical unless watchdog shows active dropouts."
            )
        logger.info(
            "[OK] Runtime verification passed (mode=VideoPattern, sequencer running)."
        )
    return all_ok


def run():
    parser = argparse.ArgumentParser(description="DLPC900 1080p Video Pattern Runtime")
    parser.add_argument(
        "--hz", type=int, default=60, help="Target Hz (60 or 120, experimental)"
    )
    parser.add_argument("--monitor", type=int, default=0, help="GLFW monitor index")
    parser.add_argument(
        "--test-checkerboard", action="store_true", help="Display static checkerboard"
    )
    parser.add_argument(
        "--test-ordering", action="store_true", help="Display bit-ordering diagnostic"
    )
    parser.add_argument(
        "--test-numbered",
        action="store_true",
        help="Display numbered region diagnostic",
    )
    parser.add_argument(
        "--test-single-pixel",
        action="store_true",
        help="Display 1x1 single pixel checkerboard (Note: creates optical diffraction bands with lasers)",
    )
    parser.add_argument(
        "--test-2x2",
        action="store_true",
        help="Display 2x2 pixel checkerboard to verify 1:1 mapping vs optical diffraction",
    )
    parser.add_argument(
        "--test-lines", action="store_true", help="Display alternating 1-pixel lines"
    )
    parser.add_argument(
        "--test-colors",
        action="store_true",
        help="Display sequence of pure RGB channels",
    )
    parser.add_argument(
        "--test-snake",
        action="store_true",
        help="Display high-speed randomly moving snake (tests 60fps dynamic refresh and triggers)",
    )
    parser.add_argument(
        "--test-clock",
        action="store_true",
        help="Display a massive high-speed microsecond clock (tests for visual stutter and latency)",
    )
    parser.add_argument(
        "--test-gradient",
        action="store_true",
        help="Display temporal duty-cycle gradient",
    )
    parser.add_argument(
        "--trigger", action="store_true", help="Software Trigger Mode (Approach A)"
    )
    parser.add_argument(
        "--runtime-seconds",
        type=int,
        default=60,
        help="Runtime for diagnostic patterns",
    )
    parser.add_argument(
        "--wake-dp", action="store_true", help="Wake DP receiver in main.py"
    )
    parser.add_argument(
        "--dual-pixel",
        action="store_true",
        help="Force dual-pixel P1-P2 mode for DLPC900 parallel input (default: single-pixel P1)",
    )
    parser.add_argument(
        "--seq-utilization",
        type=float,
        default=DEFAULT_SEQUENCE_UTILIZATION,
        help=(
            "Fraction of the safe frame budget allocated to LUT exposure timing (0<value<=1). "
            "Lower values increase idle headroom and improve robustness."
        ),
    )
    parser.add_argument(
        "--trig2-frame-zero",
        action="store_true",
        help=(
            "Emit TRIG_OUT_2 only on LUT bitplane 0 (single frame anchor). "
            "Default mode emits TRIG_OUT_2 on every bitplane."
        ),
    )
    parser.add_argument(
        "--abort-recover-cooldown",
        type=float,
        default=8.0,
        help="Seconds between automatic abort recovery attempts while runtime watchdog detects sequencer abort.",
    )
    parser.add_argument(
        "--no-auto-recover-abort",
        action="store_true",
        help="Disable automatic sequencer re-arm attempts when abort bit is detected during runtime.",
    )
    parser.add_argument(
        "--capture",
        type=str,
        help="Save the generated packed frames to an mp4 video (e.g. test.mp4)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose diagnostic logging"
    )
    args = parser.parse_args()

    # Configure centralized logger
    setup_logger(args.verbose)

    if args.hz not in (60, 120):
        logger.error(f"Unsupported Hz: {args.hz}. Only 60Hz and 120Hz are supported.")
        raise SystemExit(f"Unsupported Hz: {args.hz}")

    if args.seq_utilization <= 0.0 or args.seq_utilization > 1.0:
        logger.error("--seq-utilization must be in the interval (0, 1].")
        raise SystemExit("Invalid --seq-utilization value")

    # Allow configuration of TARGET_HZ
    target_hz = args.hz

    dlpc = None
    engine = None
    try:
        logger.info("[+] Initializing DLPC900...")
        dlpc = DLPC900()

        if args.wake_dp:
            logger.info("[+] Waking up DisplayPort receiver...")
            dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        sequence_state = configure_dlpc900_for_video_pattern(
            dlpc,
            target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
        )

        log_board_snapshot(dlpc, "POST-CONFIG (before GL stream)")

        from pattern_engine import PatternEngine

        engine = PatternEngine(monitor_index=args.monitor, fps=target_hz)

        logger.info(f"[+] Holding output for {args.runtime_seconds} seconds...")

        if args.trigger:
            logger.info("[+] Software Trigger Mode (Approach A) Active.")
            logger.info(
                "    Press spacebar to trigger 1 frame of pattern sequence, or ESC to exit."
            )

            # Start with black
            black_patterns = engine.generate_solid(0)
            black_frame = engine.pack_patterns(black_patterns)

            # The pattern to trigger
            if args.test_checkerboard:
                trig_patterns = engine.generate_checkerboard()
            elif args.test_numbered:
                from debug_scripts.debug_numbered_regions import generate_numbered_regions

                numbered_rgb = generate_numbered_regions(
                    1920, 1080, grid_cols=6, grid_rows=4
                )
                trig_patterns = engine.rgb_to_binary_patterns(numbered_rgb)
            elif args.test_single_pixel:
                trig_patterns = engine.generate_checkerboard(block_size=1)
            elif args.test_2x2:
                trig_patterns = engine.generate_checkerboard(block_size=2)
            elif args.test_lines:
                trig_patterns = engine.generate_lines()
            elif args.test_colors:
                trig_patterns = engine.rgb_to_binary_patterns(generate_solid_color(0))
            elif args.test_gradient:
                trig_patterns = engine.generate_gradient()
            else:
                trig_patterns = engine.generate_checkerboard()

            trig_frame = engine.pack_patterns(trig_patterns)

            end_t = time.time() + args.runtime_seconds
            triggered = False
            while time.time() < end_t and not engine.should_close():
                if engine.check_trigger_key():
                    logger.info("[!] Triggering sequence...")
                    engine.display_frame(trig_frame)
                    triggered = True
                else:
                    engine.display_frame(black_frame)

        else:
            # Generate initial frame based on test mode
            frame = None
            if args.test_ordering:
                logger.info("[+] Starting Diagnostic Mode: Bit Ordering Sweep...")
                patterns = engine.generate_ordering_diagnostic_patterns(1920, 1080)
            elif args.test_numbered:
                logger.info(
                    "[+] Starting Diagnostic Mode: Numbered Regions (6x4 grid)..."
                )
                from debug_scripts.debug_numbered_regions import generate_numbered_regions

                numbered_rgb = generate_numbered_regions(
                    1920, 1080, grid_cols=6, grid_rows=4
                )
                patterns = engine.rgb_to_binary_patterns(numbered_rgb)
            elif args.test_single_pixel:
                logger.info("[+] Starting Diagnostic Mode: 1x1 Single Pixel...")
                patterns = engine.generate_checkerboard(block_size=1)
            elif args.test_2x2:
                logger.info("[+] Starting Diagnostic Mode: 2x2 Checkerboard...")
                patterns = engine.generate_checkerboard(block_size=2)
            elif args.test_lines:
                logger.info("[+] Starting Diagnostic Mode: 1-pixel Lines...")
                patterns = engine.generate_lines()
            elif args.test_colors:
                logger.info("[+] Starting Diagnostic Mode: Color Channels (R/G/B)...")
                patterns = engine.rgb_to_binary_patterns(generate_solid_color(0))
            elif args.test_snake:
                logger.info("[+] Starting Diagnostic Mode: 60FPS Snake...")
                # The snake generates a pre-packed frame directly
                patterns = None
            elif args.test_clock:
                logger.info("[+] Starting Diagnostic Mode: Microsecond Clock...")
                patterns = None
            elif args.test_gradient:
                logger.info("[+] Starting Diagnostic Mode: Temporal Gradient...")
                patterns = engine.generate_gradient()
            else:
                logger.info("[+] Starting Diagnostic Mode: Static Checkerboard...")
                patterns = engine.generate_checkerboard()

            if patterns is not None:
                frame = engine.pack_patterns(patterns)
            elif args.test_snake:
                frame = engine.generate_snake_frame()
            elif args.test_clock:
                frame = engine.generate_clock_frame()

            if frame is None:
                raise RuntimeError("No initial frame generated for the selected mode.")
                
            engine.display_frame(frame)

            time.sleep(1.0)
            log_board_snapshot(dlpc, "POST-FIRST-FRAME (after GL stream)")
            if not verify_runtime_state(dlpc):
                raise RuntimeError(
                    "Runtime state check failed after first frame. "
                    "Triggers are likely unavailable because mode 2/sequencer/lock is not valid."
                )

            # Pre-generate frames for dynamic patterns to prevent stuttering in the render loop
            solid_r = frame
            solid_g = frame
            solid_b = frame
            if args.test_colors:
                solid_r = engine.pack_patterns(
                    engine.rgb_to_binary_patterns(generate_solid_color(0))
                )
                solid_g = engine.pack_patterns(
                    engine.rgb_to_binary_patterns(generate_solid_color(1))
                )
                solid_b = engine.pack_patterns(
                    engine.rgb_to_binary_patterns(generate_solid_color(2))
                )
            elif args.test_snake:
                # We will generate this on the fly, but we need an initial frame
                frame = engine.generate_snake_frame()
            elif args.test_clock:
                frame = engine.generate_clock_frame()

            video_out = None
            if args.capture and cv2 is not None:
                logger.info(f"[+] Recording packed frames to {args.capture}")
                video_writer_fourcc = getattr(cv2, "VideoWriter_fourcc", None)
                if video_writer_fourcc is None:
                    raise RuntimeError("OpenCV does not expose VideoWriter_fourcc in this environment.")
                fourcc = video_writer_fourcc(*"mp4v")
                video_writer_cls = getattr(cv2, "VideoWriter", None)
                if video_writer_cls is None:
                    raise RuntimeError("OpenCV does not expose VideoWriter in this environment.")
                video_out = video_writer_cls(
                    args.capture, fourcc, target_hz, (1920, 1080), isColor=True
                )
            elif args.capture and cv2 is None:
                logger.warning(
                    "[WARNING] Cannot capture video, opencv-python is not installed."
                )

            # ALWAYS render in a loop to keep OpenGL / VSYNC / X11 alive
            end_t = time.time() + args.runtime_seconds
            watchdog_interval_s = 2.0 if args.verbose else 0.0
            watchdog_last = time.monotonic()
            last_abort_recover_at = 0.0
            while time.time() < end_t and not engine.should_close():
                if args.test_colors:
                    sec = int(time.time() * 2) % 3
                    if sec == 0:
                        frame = solid_r
                    elif sec == 1:
                        frame = solid_g
                    else:
                        frame = solid_b
                elif args.test_snake:
                    # Generate the next frame dynamically (~1ms execution time)
                    frame = engine.generate_snake_frame()
                elif args.test_clock:
                    frame = engine.generate_clock_frame()

                # Re-display the frame to prevent X11 from blanking the unresponsive window
                engine.display_frame(frame)

                if watchdog_interval_s > 0.0:
                    now_monotonic = time.monotonic()
                    if (now_monotonic - watchdog_last) >= watchdog_interval_s:
                        ms = dlpc.get_main_status() or {}
                        mode, _ = dlpc.get_display_mode()
                        hw = dlpc.get_hardware_status()
                        hw_txt = f"0x{hw:02X}" if hw is not None else "None"
                        logger.debug(
                            f"[WATCHDOG] mode={mode} seq={bool(ms.get('sequencer_running', False))} "
                            f"lock={bool(ms.get('external_source_locked', False))} hw={hw_txt}"
                        )

                        auto_recover_abort = not args.no_auto_recover_abort
                        has_abort = bool(hw & 0x40) if hw is not None else False
                        seq_actually_stopped = not bool(ms.get('sequencer_running', True))
                        if auto_recover_abort and has_abort and seq_actually_stopped:
                            if (now_monotonic - last_abort_recover_at) >= args.abort_recover_cooldown:
                                logger.warning(
                                    "[WATCHDOG] Sequencer abort bit detected; attempting automatic sequence re-arm."
                                )
                                try:
                                    dlpc.start_pattern_display(0)
                                    time.sleep(0.05)
                                    if not ensure_video_pattern_mode(dlpc, retries=2, poll_timeout_s=1.0):
                                        logger.warning(
                                            "[WATCHDOG] Auto-recover failed to latch Video Pattern Mode before re-arm."
                                        )
                                    else:
                                        apply_pattern_sequence(dlpc, sequence_state["entries"])
                                        logger.warning("[WATCHDOG] Auto-recover sequence re-arm issued.")
                                except Exception as recover_exc:
                                    logger.warning(f"[WATCHDOG] Auto-recover failed: {recover_exc}")
                                finally:
                                    last_abort_recover_at = now_monotonic

                        watchdog_last = now_monotonic

                if video_out is not None:
                    if cv2 is None:
                        raise RuntimeError("OpenCV capture path requested but cv2 is unavailable.")
                    cvt_color = getattr(cv2, "cvtColor", None)
                    color_rgb2bgr = getattr(cv2, "COLOR_RGB2BGR", None)
                    if cvt_color is None or color_rgb2bgr is None:
                        raise RuntimeError("OpenCV color conversion APIs are unavailable in this environment.")
                    # Convert RGB (OpenGL format) to BGR (OpenCV format)
                    bgr_frame = cvt_color(frame, color_rgb2bgr)
                    video_out.write(bgr_frame)

            if video_out is not None:
                video_out.release()
                logger.info(f"[+] Video saved to {args.capture}")

    except Exception as exc:
        logger.exception(f"[ERROR] Runtime failed: {exc}")
    finally:
        logger.info("[+] Cleaning up...")
        if dlpc is not None:
            dlpc.start_pattern_display(0)
            dlpc.set_display_mode(0x00)
            dlpc.apply_block_lock_workaround()
        if engine is not None:
            engine.cleanup()


if __name__ == "__main__":
    run()
