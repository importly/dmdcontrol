"""DLPC900 setup, status, LUT, and verification helpers."""

import time

from config import (
    BITPLANES,
    DEFAULT_SEQUENCE_UTILIZATION,
    INTER_PATTERN_DARK_US,
    MAX_BINARY_RATE_HZ_DLP6500,
    MAX_MEASURED_VSYNC_DEVIATION_RATIO,
    MIN_EXPOSURE_US,
    SAFE_MARGIN_US,
)
from logger import logger


def _format_hw(hw):
    return f"0x{hw:02X}" if hw is not None else "??"


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

    fw = dlpc.get_firmware_version()
    if fw:
        logger.debug(
            f"Firmware Version:     app={fw['app']['str']} api={fw['api']['str']} "
            f"sw_cfg={fw['sw_cfg']['str']} seq_cfg={fw['seq_cfg']['str']}"
        )
        if fw["app"]["major"] <= 5 and fw["app"]["minor"] == 0:
            logger.warning(
                "Firmware <= 5.0.x: DLPT028 block-lock workaround required (park/unpark after mode change)."
            )
        else:
            logger.debug(
                f"  Firmware {fw['app']['str']} > 5.0.x: DLPT028 errata fixed. Park/unpark may be unnecessary."
            )

    cs = dlpc.get_channel_swap()
    if cs:
        logger.debug(
            f"Channel Swap:         {cs['swap_label']} (port {cs['port']}, raw {cs['raw']})"
        )
        if cs["swap_label"] != "ABC":
            logger.debug(
                f"  Note: non-default channel swap '{cs['swap_label']}' active. Affects RGB->bitplane pin mapping."
            )

    logger.debug("=" * 66)


def build_lut_entries(
    dlpc,
    target_hz,
    sequence_utilization=DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero=False,
):
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
                "Ignoring unstable measured VSYNC %.3f Hz (target %.3f Hz, deviation %.1f%%). "
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
            f"Mode readback shows {mode}, not 2! Retrying mode transition ({attempt}/{retries})..."
        )
        dlpc.set_display_mode(0x02)

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


def apply_pattern_sequence(dlpc, entries, frame_pump=None):
    # DLPU018J §2.4.4.3.4: Pattern Display LUT Reorder (0x1A32) is "only applicable
    # in Pre-stored Pattern Mode and Pattern On-The-Fly Mode" — NOT Video Pattern Mode.
    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(len(entries), repeat=True)
    if frame_pump is not None:
        frame_pump()
    dlpc.start_pattern_display(2)
    time.sleep(0.2)

    # Non-multiples of 16.67ms to avoid landing on same VSYNC phase each attempt.
    _RETRY_DELAYS = [0.37, 0.73, 1.17, 1.83, 2.53]
    for attempt in range(1, len(_RETRY_DELAYS) + 1):
        hw = dlpc.get_hardware_status()
        if hw is None or not (hw & 0x40):
            if attempt > 1:
                logger.info(f"[+] Abort latch cleared on attempt {attempt} (hw={_format_hw(hw)}). Sequencer running.")
            break
        logger.warning(
            f"Abort latch (hw=0x{hw:02X}) after start attempt {attempt}. "
            f"Clearing: stop -> park/unpark -> {_RETRY_DELAYS[attempt-1]:.2f}s -> resend LUT -> restart."
        )
        dlpc.start_pattern_display(0)
        time.sleep(0.1)
        dlpc.apply_block_lock_workaround()
        time.sleep(_RETRY_DELAYS[attempt - 1])
        dlpc.set_pattern_lut_definition(entries)
        dlpc.set_pattern_lut_config(len(entries), repeat=True)
        if frame_pump is not None:
            frame_pump()
        dlpc.start_pattern_display(2)
        time.sleep(0.2)
    else:
        hw_final = dlpc.get_hardware_status()
        logger.error(
            f"Abort latch persists (hw={_format_hw(hw_final)}) after {len(_RETRY_DELAYS)} retries. "
            "Triggers unreliable. Power cycle DLPC900."
        )


def configure_dlpc900_for_video_pattern(
    dlpc,
    target_hz=60,
    dual_pixel=False,
    sequence_utilization=DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero=False,
    pre_arm_callback=None,
    frame_pump=None,
):
    logger.info(
        f"[+] Configuring DLPC900 for 1920x1080 @ {target_hz}Hz Video Pattern Mode ({BITPLANES} bit-planes)..."
    )
    logger.debug("Following TI documentation sequence (DLPU018J Section 5.1)...")

    dlpc.start_pattern_display(0)
    time.sleep(0.2)

    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    # DLPU018J p.56: must enter Video Mode (0) with desired source BEFORE switching to Mode 2.
    logger.debug("  - Entering Video Mode (0) with DisplayPort source...")
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)
    dlpc.toggle_dual_pixel_mode(bool(dual_pixel))
    logger.info(
        f"[+] Parallel input pixel mode: {'Dual P1-P2' if dual_pixel else 'Single P1'}"
    )

    # Force full 1920x1080 active area — otherwise DLPC900 may use a stale Flash-resident crop.
    logger.debug("  - Forcing Input Display Resolution to 1920x1080...")
    dlpc.set_input_display_resolution(0, 0, 1920, 1080)

    dlpc.apply_block_lock_workaround()

    logger.info("[+] Waiting for external source sync lock...")
    if wait_for_external_lock(dlpc, timeout_s=4.0):
        logger.info("[+] External source lock acquired. Waiting 3s for video buffer to fill...")
        time.sleep(3)
        logger.info("[+] Video buffer dwell complete.")
    else:
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "External source sync lock was not acquired. "
            f"Main status: {ms}. Without lock, Video Pattern Mode and trigger outputs are unreliable."
        )

    # Per DLPU018J p.56: mode transition ~300ms. TI ref GUI uses 500ms.
    logger.debug("  - Switching to Video Pattern Mode (0x02)...")
    dlpc.set_display_mode(0x02)
    logger.debug("  - Waiting 500ms for mode transition...")
    time.sleep(0.5)

    # Stop before park: required in Video Pattern Mode or firmware latches abort bit 0x40.
    dlpc.start_pattern_display(0)
    time.sleep(0.05)
    dlpc.apply_block_lock_workaround()
    time.sleep(0.1)

    mode, _ = dlpc.get_display_mode()
    logger.debug(f"  - Display mode readback: {mode} (expected: 2)")

    if not ensure_video_pattern_mode(dlpc, retries=3, poll_timeout_s=1.5):
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            "Failed to enter Video Pattern Mode (mode 2) after retries. "
            f"Mode readback: {mode}, main status: {ms}. Trigger outputs are disabled in Video Mode."
        )

    # Mode transition + park/unpark can reset DP receiver. Re-lock before arming sequencer.
    logger.info("[+] Waiting for external source lock in Video Pattern Mode...")
    if not wait_for_external_lock(dlpc, timeout_s=6.0):
        logger.warning("External lock not re-acquired in mode 2. Proceeding — triggers may be unreliable.")
    else:
        logger.info("[+] External lock confirmed in mode 2. Waiting 2s for DP pipeline to stabilize...")
        time.sleep(2.0)

    # DLPU018J Table 2-118/2-120: byte 0 bit 0 = polarity. No enable bit.
    # Non-inverted constraint: rising_delay <= falling_delay. Min pulse width: 20us.
    dlpc.configure_trigger_out_1(polarity_high=True, rising_delay_us=5, falling_delay_us=20)
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_1 config sent. Last error: {err}")

    dlpc.configure_trigger_out_2(polarity_high=True, rising_delay_us=0, falling_delay_us=20)
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_2 config sent. Last error: {err}")

    t1 = dlpc.get_trigger_out_1()
    t2 = dlpc.get_trigger_out_2()
    logger.info(f"  - TRIG_OUT_1 readback: {t1}")
    logger.info(f"  - TRIG_OUT_2 readback: {t2}")

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
            f"Source VSYNC is {timing['measured_frame_hz']:.3f} Hz while --hz is {target_hz} Hz. "
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
        logger.info("[SCOPE] Expected TRIG_OUT_2: ~20us pulse width, triggered only on bitplane 0.")
        logger.info(f"[SCOPE] TRIG_OUT_2 mode: frame_zero anchor (~{timing['effective_frame_hz']:.3f} pulses/s).")
    else:
        logger.info("[SCOPE] Expected TRIG_OUT_2: ~20us pulse width, active at each bitplane start.")
        logger.info(f"[SCOPE] TRIG_OUT_2 mode: per_bitplane (~{timing['effective_binary_rate_hz']:.1f} pulses/s).")
    logger.info(
        f"[SCOPE] Expected TRIG_OUT_1: ~{timing['effective_frame_hz']:.3f} pulses/s. "
        "With dark=0us, pulse may appear as a wide frame-level gate."
    )

    # Empirically: arming before DLPC900 processes several VSYNCs in mode 2 -> forced-swap (hw 0x08) -> abort (0x40).
    logger.debug("  - Final VSYNC settling wait (1s)...")
    time.sleep(1.0)

    # GL must be rendering when start_pattern_display(2) fires — stale DP frame -> forced-swap.
    if pre_arm_callback is not None:
        pre_arm_callback()

    logger.info(f"[+] Applying LUT reorder with {len(entries)} entries...")
    apply_pattern_sequence(dlpc, entries, frame_pump=frame_pump)

    logger.info("[+] Pattern sequencer start command issued.")

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
            f"Hardware status indicates sequencer abort/error bits set (0x{hw:02X}). "
            "These bits can be latched from prior faults; monitor runtime watchdog for live state changes."
        )

    return {"entries": entries, "timing": timing}


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
        logger.warning("Runtime verification checks failed!")
        logger.warning("           Video Pattern Mode (2), source lock, or sequencer health check failed.")
        logger.warning("           Check DisplayPort sync lock and mode transition timing.")
        if hw is not None:
            logger.warning(f"           Hardware status raw: 0x{hw:02X}")
    else:
        if seq_abort or seq_error:
            logger.warning(
                f"Runtime health bits indicate abort/error flags are set (0x{hw:02X}) despite mode/sequencer lock. "
                "Treat as sticky/historical unless watchdog shows active dropouts."
            )
        logger.info("[OK] Runtime verification passed (mode=VideoPattern, sequencer running).")
    return all_ok
