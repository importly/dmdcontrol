"""DLPC900 setup, status, LUT, and verification helpers."""

import threading
import time

from dmdcontrol.support.constants import (
    BITPLANES,
    DEFAULT_HZ,
    DEFAULT_SEQUENCE_UTILIZATION,
    DMD_HEIGHT,
    DMD_WIDTH,
    INTER_PATTERN_DARK_US,
    MAX_BINARY_RATE_HZ_DLP6500,
    MAX_MEASURED_VSYNC_DEVIATION_RATIO,
    MIN_EXPOSURE_US,
    SAFE_MARGIN_US,
    TRIGGER_OUT_DELAY_MAX_US,
    TRIGGER_OUT_DELAY_MIN_US,
    TRIGGER_OUT_PULSE_WIDTH_US,
    TRIGGER_OUT_RISING_DELAY_MAX_US,
)
from dmdcontrol.support.logging import logger


def _format_hw(hw):
    if hw is None:
        return "??"
    # DLPU018J Table 2-21. Bit 5 is reserved (commonly reads 1).
    bits = []
    if hw & 0x01: bits.append("init_ok")
    if hw & 0x02: bits.append("dmd_compat_err")
    if hw & 0x04: bits.append("dmd_reset_err")
    if hw & 0x08: bits.append("forced_swap")
    if hw & 0x10: bits.append("bit4")
    if hw & 0x20: bits.append("bit5_rsvd")
    if hw & 0x40: bits.append("ABORT")
    if hw & 0x80: bits.append("SEQ_ERR")
    return f"0x{hw:02X}[{'|'.join(bits) if bits else 'clean'}]"


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
            f"  Total:              {dd['total_pixels_per_line']} x {dd['total_lines_per_frame']}")
        logger.debug(
            f"  Active:             {dd['active_pixels_per_line']} x {dd['active_lines_per_frame']}"
        )
        logger.debug(
            f"  First pixel:        ({dd['first_active_pixel']}, {dd['first_active_line']})")
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
            f"sw_cfg={fw['sw_cfg']['str']} seq_cfg={fw['seq_cfg']['str']}")
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
            f"Channel Swap:         {cs['swap_label']} (port {cs['port']}, raw {cs['raw']})")
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
    entries_count=None,
    per_entry_exposure_us=None,
    dark_time_us=None,
):
    if target_hz <= 0:
        raise ValueError("target_hz must be positive")
    if sequence_utilization <= 0.0 or sequence_utilization > 1.0:
        raise ValueError("sequence_utilization must be in the interval (0, 1].")

    actual_dark_us = INTER_PATTERN_DARK_US if dark_time_us is None else dark_time_us
    if actual_dark_us < 0:
        raise ValueError("dark_time_us must be non-negative")

    measured_frame_hz = None
    dd = dlpc.get_display_dimensions()
    if (dd and dd.get("pixel_clock_khz") and dd.get("total_pixels_per_line")
            and dd.get("total_lines_per_frame")):
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

    min_segment_us = MIN_EXPOSURE_US + actual_dark_us
    usable_frame_period_us = safe_frame_period_us * sequence_utilization

    if entries_count is None and per_entry_exposure_us is not None:
        if per_entry_exposure_us < MIN_EXPOSURE_US:
            raise ValueError(
                f"per_entry_exposure_us ({per_entry_exposure_us}) is below MIN_EXPOSURE_US "
                f"({MIN_EXPOSURE_US}).")
        requested_segment_us = per_entry_exposure_us + actual_dark_us
        entries_count = int(usable_frame_period_us // requested_segment_us)
        entries_count = max(1, min(BITPLANES, entries_count))
    elif entries_count is None:
        entries_count = BITPLANES
    if entries_count < 1 or entries_count > BITPLANES:
        raise ValueError(f"entries_count ({entries_count}) must be in [1, {BITPLANES}].")

    requested_binary_rate_hz = float(target_hz) * entries_count
    if requested_binary_rate_hz > MAX_BINARY_RATE_HZ_DLP6500:
        raise ValueError(
            f"Requested binary rate {requested_binary_rate_hz:.1f} Hz exceeds "
            f"DLP6500 1-bit limit (~{MAX_BINARY_RATE_HZ_DLP6500} Hz).")

    effective_binary_rate_hz = effective_frame_hz * entries_count
    if effective_binary_rate_hz > MAX_BINARY_RATE_HZ_DLP6500:
        raise ValueError(
            f"Measured source binary rate {effective_binary_rate_hz:.1f} Hz exceeds "
            f"DLP6500 1-bit limit (~{MAX_BINARY_RATE_HZ_DLP6500} Hz).")

    if per_entry_exposure_us is not None:
        if per_entry_exposure_us < MIN_EXPOSURE_US:
            raise ValueError(
                f"per_entry_exposure_us ({per_entry_exposure_us}) is below MIN_EXPOSURE_US "
                f"({MIN_EXPOSURE_US}).")
        total_needed_us = (per_entry_exposure_us + actual_dark_us) * entries_count
        if total_needed_us > usable_frame_period_us:
            raise ValueError(
                f"{entries_count} LUT entries at {per_entry_exposure_us} us exposure need "
                f"{total_needed_us:.1f} us per VSYNC but only {usable_frame_period_us:.1f} us is "
                f"usable (frame_period {frame_period_us:.1f} us, margin {SAFE_MARGIN_US} us, "
                f"utilization {sequence_utilization}).")
        exposure_us = int(per_entry_exposure_us)
    else:
        segment_budget_us = usable_frame_period_us / entries_count
        if segment_budget_us < min_segment_us:
            max_safe_hz = 1_000_000.0 / (
                (entries_count * min_segment_us / sequence_utilization) + SAFE_MARGIN_US)
            raise ValueError(
                f"Requested sequence exceeds VSYNC budget: each pattern has {segment_budget_us:.2f} us "
                f"but needs >= {min_segment_us} us (exposure {MIN_EXPOSURE_US} us + dark {actual_dark_us} us). "
                f"Reduce source frame rate to <= {max_safe_hz:.2f} Hz.")

        segment_us = int(usable_frame_period_us / entries_count)
        exposure_us = segment_us - actual_dark_us
        if exposure_us < MIN_EXPOSURE_US:
            max_safe_hz = 1_000_000.0 / (
                (entries_count * min_segment_us / sequence_utilization) + SAFE_MARGIN_US)
            raise ValueError(
                f"Computed exposure {exposure_us} us is below minimum {MIN_EXPOSURE_US} us. "
                f"Reduce source frame rate to <= {max_safe_hz:.2f} Hz.")

    total_sequence_us = (exposure_us + actual_dark_us) * entries_count
    idle_headroom_us = frame_period_us - total_sequence_us

    entries = []
    for bit_pos in range(entries_count):
        clear_flag = bit_pos == (entries_count - 1)
        trig2_disable = (bit_pos != 0) if trig2_frame_zero else False
        entries.append(
            (
                bit_pos,
                exposure_us,
                clear_flag,
                1,
                7,
                actual_dark_us,
                trig2_disable,
                bit_pos,
            ))

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
        "dark_us": actual_dark_us,
        "total_sequence_us": total_sequence_us,
        "idle_headroom_us": idle_headroom_us,
        "entries_count": entries_count,
    }
    return entries, timing


def compute_trigger_out_2_timing(
    rising_delay_us=0,
    pulse_width_us=TRIGGER_OUT_PULSE_WIDTH_US,
):
    if not isinstance(rising_delay_us, int):
        raise ValueError("rising_delay_us must be an integer")
    if not isinstance(pulse_width_us, int):
        raise ValueError("pulse_width_us must be an integer")
    if pulse_width_us < 1:
        raise ValueError("pulse_width_us must be positive")

    falling_delay_us = rising_delay_us + pulse_width_us
    max_rising_delay_us = TRIGGER_OUT_RISING_DELAY_MAX_US
    if not (TRIGGER_OUT_DELAY_MIN_US <= rising_delay_us <= max_rising_delay_us):
        raise ValueError(
            f"rising_delay_us must be between {TRIGGER_OUT_DELAY_MIN_US} and "
            f"{max_rising_delay_us}")
    if not (TRIGGER_OUT_DELAY_MIN_US <= falling_delay_us <= TRIGGER_OUT_DELAY_MAX_US):
        raise ValueError(
            f"falling_delay_us must be between {TRIGGER_OUT_DELAY_MIN_US} and "
            f"{TRIGGER_OUT_DELAY_MAX_US}")
    return {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": rising_delay_us,
        "falling_delay_us": falling_delay_us,
        "pulse_width_us": pulse_width_us,
    }


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


def _bit6_is_cosmetic(dlpc, hw):
    """Return True when bit 6 is latched but all real health signals are good."""
    if hw is None or not (hw & 0x40):
        return False
    if hw & 0x88:  # forced_swap or SEQ_ERR are real fault paths.
        return False
    ms = dlpc.get_main_status() or {}
    mode, _ = dlpc.get_display_mode()
    return bool(
        mode == 2 and ms.get("sequencer_running") and ms.get("external_source_locked")
        and ms.get("port1_syncs_valid"))


def ensure_video_pattern_mode(dlpc, retries=3, poll_timeout_s=1.2):
    mode, _ = dlpc.get_display_mode()
    if mode == 2:
        return True

    for attempt in range(1, retries + 1):
        logger.warning(
            f"Mode readback shows {mode}, not 2! Retrying mode transition ({attempt}/{retries})...")
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


def load_pattern_sequence(dlpc, entries):
    # DLPU018J §2.4.4.3.4: Pattern Display LUT Reorder (0x1A32) is "only applicable
    # in Pre-stored Pattern Mode and Pattern On-The-Fly Mode" — NOT Video Pattern Mode.

    # Pre-LUT snapshot. If ABORT is already set here, the latch is sticky from
    # a prior boot/run — distinguishes "we caused it" from "it was already there".
    hw_pre = dlpc.get_hardware_status()
    logger.debug(f"  [arm] hw pre-LUT  = {_format_hw(hw_pre)}")

    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(len(entries), repeat=True)
    hw_after_lut = dlpc.get_hardware_status()
    logger.debug(f"  [arm] hw post-LUT = {_format_hw(hw_after_lut)}")


def start_loaded_pattern_sequence(dlpc, post_start_delay_s=0.2):
    dlpc.start_pattern_display(2)
    if post_start_delay_s > 0:
        time.sleep(post_start_delay_s)


def start_loaded_pattern_sequences(
    dlpc_a,
    dlpc_b,
    post_start_delay_s=0.2,
    verify=False,
):
    barrier = threading.Barrier(3)
    errors = []

    def _start_one(label, dlpc):
        try:
            barrier.wait()
            dlpc.start_pattern_display(2)
        except Exception as exc:
            errors.append((label, exc))

    threads = [
        threading.Thread(target=_start_one,
                         args=("A",
                               dlpc_a),
                         daemon=True),
        threading.Thread(target=_start_one,
                         args=("B",
                               dlpc_b),
                         daemon=True),
    ]
    for thread in threads:
        thread.start()

    barrier.wait()
    for thread in threads:
        thread.join()

    if errors:
        detail = "; ".join(f"{label}: {exc}" for label, exc in errors)
        raise RuntimeError(f"Paired sequencer start failed: {detail}")

    if post_start_delay_s > 0:
        time.sleep(post_start_delay_s)

    if verify:
        verify_started_pattern_sequence(dlpc_a, label="A")
        verify_started_pattern_sequence(dlpc_b, label="B")


def verify_started_pattern_sequence(dlpc, label="DLPC900"):
    if not ensure_video_pattern_mode(dlpc, retries=2, poll_timeout_s=1.0):
        mode, _ = dlpc.get_display_mode()
        ms = dlpc.get_main_status() or {}
        raise RuntimeError(
            f"{label} dropped out of Video Pattern Mode after sequencer start. "
            f"Mode readback: {mode}, main status: {ms}.")

    if not wait_for_sequencer_running(dlpc, timeout_s=1.5):
        ms = dlpc.get_main_status() or {}
        hw = dlpc.get_hardware_status()
        raise RuntimeError(
            f"{label} pattern sequencer did not report running after start command. "
            f"Main status: {ms}, hardware status: {hw}.")

    hw = dlpc.get_hardware_status()
    if hw is not None and (hw & 0x80):
        logger.warning(
            f"{label} hardware status sequence-error bit set (hw=0x{hw:02X}). "
            "Sequencer has reported a runtime error condition.")
    elif hw is not None and (hw & 0x40):
        logger.debug(
            f"  {label} post-config hw=0x{hw:02X}. "
            "Bit 6 latched (cosmetic, set by Pattern Stop).")
    return hw


def apply_pattern_sequence(dlpc, entries, frame_pump=None):
    load_pattern_sequence(dlpc, entries)

    if frame_pump is not None:
        frame_pump()
    start_loaded_pattern_sequence(dlpc)

    # hw bit 6 (DLPU018J "ABORT") is set by Pattern Display Stop and can persist
    # after a healthy restart. Only retry when bit 6 is paired with real unhealthy
    # state: forced_swap, SEQ_ERR, mode drop, stopped sequencer, or lost sync.
    _RETRY_DELAYS = [0.37, 0.73, 1.17, 1.83, 2.53]
    for attempt in range(1, len(_RETRY_DELAYS) + 1):
        hw = dlpc.get_hardware_status()
        if hw is None or not (hw & 0x40):
            if attempt > 1:
                logger.debug(f"  [arm] bit-6 cleared on attempt {attempt} (hw={_format_hw(hw)}).")
            break

        if _bit6_is_cosmetic(dlpc, hw):
            logger.debug(
                f"  [arm] bit-6 latched but health checks are good "
                f"(hw={_format_hw(hw)}); skipping retry churn.")
            break

        err_code = dlpc.get_last_error()
        err_desc = dlpc.get_error_description()
        logger.debug(
            f"  [arm] bit-6 latched hw={_format_hw(hw)} after start attempt {attempt}. "
            f"last_err={err_code!r} desc={err_desc!r}. "
            f"Stop -> park/unpark -> {_RETRY_DELAYS[attempt - 1]:.2f}s -> resend LUT -> restart.")
        dlpc.start_pattern_display(0)
        time.sleep(0.1)
        hw_after_stop = dlpc.get_hardware_status()
        logger.debug(f"  [retry {attempt}] hw post-stop    = {_format_hw(hw_after_stop)}")
        dlpc.apply_block_lock_workaround()
        hw_after_pp = dlpc.get_hardware_status()
        logger.debug(f"  [retry {attempt}] hw post-park    = {_format_hw(hw_after_pp)}")
        time.sleep(_RETRY_DELAYS[attempt - 1])
        dlpc.set_pattern_lut_definition(entries)
        dlpc.set_pattern_lut_config(len(entries), repeat=True)
        if frame_pump is not None:
            frame_pump()
        dlpc.start_pattern_display(2)
        time.sleep(0.2)
        hw_after_start = dlpc.get_hardware_status()
        logger.debug(f"  [retry {attempt}] hw post-restart = {_format_hw(hw_after_start)}")
    else:
        hw_final = dlpc.get_hardware_status()
        err_code = dlpc.get_last_error()
        err_desc = dlpc.get_error_description()
        logger.warning(
            f"[+] Unhealthy bit-6 state still latched (hw={_format_hw(hw_final)}) "
            f"after {len(_RETRY_DELAYS)} retries. "
            f"last_err={err_code!r} desc={err_desc!r}. "
            "Check sequencer_running, external_source_locked, port1_syncs_valid, forced_swap, and SEQ_ERR."
        )


def prepare_dlpc900_for_video_pattern(
    dlpc,
    target_hz=DEFAULT_HZ,
    dual_pixel=False,
    sequence_utilization=DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero=False,
    entries_count=None,
    per_entry_exposure_us=None,
    trigger_out_2_rising_delay_us=0,
    dark_time_us=None,
):
    actual_entries = entries_count if entries_count is not None else BITPLANES
    logger.info(
        f"[+] Configuring DLPC900 for {DMD_WIDTH}x{DMD_HEIGHT} @ {target_hz}Hz Video Pattern Mode "
        f"({actual_entries} LUT entr{'y' if actual_entries == 1 else 'ies'} per VSYNC)...")
    logger.debug("Following TI documentation sequence (DLPU018J Section 5.1)...")

    # First-touch hw status. NOTE: hw bit 6 ("ABORT" per DLPU018J Table 2-21)
    # is verified empirically to double as a "no clean active pattern sequence"
    # state flag. It persists across barrel power cycles and is set whenever
    # Pattern Display Mode (2) is not running cleanly. Treat as informational
    # unless paired with sequencer_running=False or forced_swap=True.
    hw_first = dlpc.get_hardware_status()
    err0_code = dlpc.get_last_error()
    err0_desc = dlpc.get_error_description()
    logger.info(
        f"[+] DLPC900 first-touch status: hw={_format_hw(hw_first)} "
        f"last_err={err0_code!r} desc={err0_desc!r}")

    # Stop pattern display ONLY if currently in Pattern Mode (2). At boot the
    # display mode defaults to 0 (Video Mode) and Pattern Stop is firmware-NACKed,
    # producing harmless but noisy WARNING. Skip the unconditional stop.
    current_mode, _ = dlpc.get_display_mode()
    if current_mode == 2:
        logger.debug(
            f"  - Pre-config stop: display already in mode {current_mode}, sending Pattern Stop...")
        dlpc.start_pattern_display(0)
        time.sleep(0.2)
    else:
        logger.debug(
            f"  - Pre-config stop skipped (display mode={current_mode}, no pattern running).")

    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    #  must enter Video Mode (0) with desired source BEFORE switching to Mode 2.
    logger.debug("  - Entering Video Mode (0) with DisplayPort source...")
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)
    dlpc.toggle_dual_pixel_mode(bool(dual_pixel))
    logger.info(f"[+] Parallel input pixel mode: {'Dual P1-P2' if dual_pixel else 'Single P1'}")

    # Force full active area — otherwise DLPC900 may use a stale Flash-resident crop.
    logger.debug(f"  - Forcing Input Display Resolution to {DMD_WIDTH}x{DMD_HEIGHT}...")
    dlpc.set_input_display_resolution(0, 0, DMD_WIDTH, DMD_HEIGHT)

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
        logger.warning(
            "External lock not re-acquired in mode 2. Proceeding — triggers may be unreliable.")
    else:
        logger.info(
            "[+] External lock confirmed in mode 2. Waiting 2s for DP pipeline to stabilize...")
        time.sleep(2.0)

    # DLPU018J Table 2-118/2-120: byte 0 bit 0 = polarity. No enable bit.
    # Non-inverted constraint: rising_delay <= falling_delay. Min pulse width: 20us.
    dlpc.configure_trigger_out_1(polarity_high=True, rising_delay_us=0, falling_delay_us=20)
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_1 config sent. Last error: {err}")

    entries, timing = build_lut_entries(
        dlpc,
        target_hz,
        sequence_utilization=sequence_utilization,
        trig2_frame_zero=trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=per_entry_exposure_us,
        dark_time_us=dark_time_us,
    )
    trigger_out_2_timing = compute_trigger_out_2_timing(
        rising_delay_us=trigger_out_2_rising_delay_us,
    )
    dlpc.configure_trigger_out_2(
        polarity_high=True,
        rising_delay_us=trigger_out_2_timing["rising_delay_us"],
        falling_delay_us=trigger_out_2_timing["falling_delay_us"],
    )
    err = dlpc.get_last_error()
    logger.debug(f"  - TRIG_OUT_2 config sent. Last error: {err}")
    timing["trigger_out_2"] = trigger_out_2_timing

    t1 = dlpc.get_trigger_out_1()
    t2 = dlpc.get_trigger_out_2()
    logger.info(f"  - TRIG_OUT_1 readback: {t1}")
    logger.info(f"  - TRIG_OUT_2 readback: {t2}")
    logger.info(
        f"[TIMING] LUT timing source: {timing['timing_source']} (effective VSYNC {timing['effective_frame_hz']:.3f} Hz)."
    )
    if timing["measured_frame_hz"] and abs(timing["measured_frame_hz"] - target_hz) > 0.5:
        logger.warning(
            f"Source VSYNC is {timing['measured_frame_hz']:.3f} Hz while --hz is {target_hz} Hz. "
            f"Sequencer timing follows source VSYNC ({timing['effective_frame_hz']:.3f} Hz).")
    logger.info(
        f"[+] LUT: {timing['entries_count']} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/{timing['usable_frame_period_us']:.1f}us "
        f"(utilization {timing['sequence_utilization']:.2f}, reserved margin {timing['safe_margin_us']:.1f}us, "
        f"idle headroom {timing['idle_headroom_us']:.1f}us from {timing['frame_period_us']:.1f}us VSYNC), "
        f"binary rate req={timing['requested_binary_rate_hz']:.1f}Hz, "
        f"effective={timing['effective_binary_rate_hz']:.1f}Hz")
    if timing["trig2_mode"] == "frame_zero":
        logger.info(
            f"[SCOPE] Expected TRIG_OUT_2: rising delay={trigger_out_2_timing['rising_delay_us']}us, "
            f"falling={trigger_out_2_timing['falling_delay_us']}us, triggered only on bitplane 0.")
        logger.info(
            f"[SCOPE] TRIG_OUT_2 mode: frame_zero anchor (~{timing['effective_frame_hz']:.3f} pulses/s)."
        )
    else:
        logger.info(
            f"[SCOPE] Expected TRIG_OUT_2: rising delay={trigger_out_2_timing['rising_delay_us']}us, "
            f"falling={trigger_out_2_timing['falling_delay_us']}us, active at each bitplane start.")
        logger.info(
            f"[SCOPE] TRIG_OUT_2 mode: per_bitplane (~{timing['effective_binary_rate_hz']:.1f} pulses/s)."
        )
    logger.info(
        f"[SCOPE] Expected TRIG_OUT_1: ~{timing['effective_frame_hz']:.3f} pulses/s. "
        "With dark=0us, pulse may appear as a wide frame-level gate.")

    # Empirically: arming before DLPC900 processes several VSYNCs in mode 2 -> forced-swap (hw 0x08) -> abort (0x40).
    logger.debug("  - Final VSYNC settling wait (1s)...")
    time.sleep(1.0)

    return {"entries": entries, "timing": timing}


def configure_dlpc900_for_video_pattern(
    dlpc,
    target_hz=DEFAULT_HZ,
    dual_pixel=False,
    sequence_utilization=DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero=False,
    pre_arm_callback=None,
    frame_pump=None,
    entries_count=None,
    per_entry_exposure_us=None,
    trigger_out_2_rising_delay_us=0,
    dark_time_us=None,
):
    sequence_state = prepare_dlpc900_for_video_pattern(
        dlpc,
        target_hz=target_hz,
        dual_pixel=dual_pixel,
        sequence_utilization=sequence_utilization,
        trig2_frame_zero=trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=per_entry_exposure_us,
        trigger_out_2_rising_delay_us=trigger_out_2_rising_delay_us,
        dark_time_us=dark_time_us,
    )

    # GL must be rendering when start_pattern_display(2) fires — stale DP frame -> forced-swap.
    if pre_arm_callback is not None:
        pre_arm_callback()

    entries = sequence_state["entries"]
    logger.info(f"[+] Applying pattern LUT with {len(entries)} entries...")
    apply_pattern_sequence(dlpc, entries, frame_pump=frame_pump)

    logger.info("[+] Pattern sequencer start command issued.")
    verify_started_pattern_sequence(dlpc)
    return sequence_state


def verify_runtime_state(dlpc):
    ms = dlpc.get_main_status() or {}
    mode, _ = dlpc.get_display_mode()
    hw = dlpc.get_hardware_status()

    seq_abort = bool(hw & 0x40) if hw is not None else False
    seq_error = bool(hw & 0x80) if hw is not None else False
    forced_swap = bool(hw & 0x08) if hw is not None else False

    hard_checks = {
        "display_mode_is_video_pattern": mode == 2,
        "sequencer_running": bool(ms.get("sequencer_running",
                                         False)),
        "forced_swap_clear": not forced_swap,
        "seq_error_clear": not seq_error,
    }
    advisory_checks = {
        "external_source_locked": bool(ms.get("external_source_locked",
                                              False)),
        "port1_syncs_valid": bool(ms.get("port1_syncs_valid",
                                         False)),
    }

    logger.debug("Verification:")
    for name, ok in hard_checks.items():
        logger.debug(f"  {name:30} {'PASS' if ok else 'FAIL'}")
    for name, ok in advisory_checks.items():
        logger.debug(f"  {name:30} {'PASS' if ok else 'WARN'}")

    hard_ok = all(hard_checks.values())
    advisory_ok = all(advisory_checks.values())
    if not hard_ok:
        logger.warning("Runtime verification hard checks failed!")
        logger.warning(
            "           Video Pattern Mode (2), sequencer running, forced-swap clear, or SEQ_ERR clear failed."
        )
        if hw is not None:
            logger.warning(f"           Hardware status raw: 0x{hw:02X}")
    else:
        if not advisory_ok:
            logger.warning(
                "Runtime verification advisory checks did not all pass; continuing because "
                "mode/sequencer/hardware error bits are healthy. Confirm TRIG_OUT_2 on scope.")
            logger.warning(
                f"           external_source_locked={advisory_checks['external_source_locked']} "
                f"port1_syncs_valid={advisory_checks['port1_syncs_valid']}")
        if seq_abort:
            # bit 6 = state-machine flag latched after every Pattern Stop; cosmetic
            logger.debug(f"  Runtime hw=0x{hw:02X}. Bit 6 latched (cosmetic, set by Pattern Stop).")
        logger.info("[OK] Runtime verification passed (mode=VideoPattern, sequencer running).")
    return hard_ok
