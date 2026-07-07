"""DLPC900 Video Pattern Mode setup, LUT loading, and sequencer start."""

from __future__ import annotations

from argparse import Namespace
from collections.abc import Callable, Sequence
import threading
import time
from typing import TYPE_CHECKING

from dmdcontrol.runtime.dlpc_status import (
    _bit6_is_cosmetic,
    _format_hw,
    ensure_video_pattern_mode,
    wait_for_external_lock,
    wait_for_sequencer_running,
)
from dmdcontrol.runtime.lut import (
    LutEntry,
    PreparedSequenceState,
    build_lut_entries,
    compute_trigger_out_2_timing,
)
from dmdcontrol.support.constants import (
    BITPLANES,
    DEFAULT_HZ,
    DEFAULT_SEQUENCE_UTILIZATION,
    DMD_HEIGHT,
    DMD_WIDTH,
)
from dmdcontrol.support.logging import logger

if TYPE_CHECKING:
    from dmdcontrol.hardware.dlpc900 import DLPC900


def warn_dark_time_video_pattern_mode(args: Namespace) -> None:
    if getattr(args, "dark_time_us", None) is None:
        return
    logger.warning(
        "--dark-time-us does not work as expected with DLPC900 Video Pattern Mode. "
        "Use explicit blank frames or blank bitplanes for visible off-time; this value is only "
        "kept for LUT timing/budget accounting.")


def load_pattern_sequence(dlpc: "DLPC900", entries: Sequence[LutEntry]) -> None:
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


def start_loaded_pattern_sequence(
    dlpc: "DLPC900",
    post_start_delay_s: float = 0.2,
) -> None:
    dlpc.start_pattern_display(2)
    if post_start_delay_s > 0:
        time.sleep(post_start_delay_s)


def start_loaded_pattern_sequences(
    dlpc_a: "DLPC900",
    dlpc_b: "DLPC900",
    post_start_delay_s: float = 0.2,
    verify: bool = False,
) -> None:
    barrier = threading.Barrier(3)
    errors: list[tuple[str, BaseException]] = []

    def _start_one(label: str, dlpc: "DLPC900") -> None:
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


def verify_started_pattern_sequence(
    dlpc: "DLPC900",
    label: str = "DLPC900",
) -> int | None:
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


def apply_pattern_sequence(
    dlpc: "DLPC900",
    entries: Sequence[LutEntry],
    frame_pump: Callable[[], None] | None = None,
) -> None:
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
    dlpc: "DLPC900",
    target_hz: float = DEFAULT_HZ,
    dual_pixel: bool = False,
    sequence_utilization: float = DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero: bool = False,
    entries_count: int | None = None,
    per_entry_exposure_us: int | None = None,
    trigger_out_2_rising_delay_us: int = 0,
    dark_time_us: int | None = None,
) -> PreparedSequenceState:
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
    logger.debug("  - Setting input pixel format to RGB888 (0)...")
    dlpc.set_input_pixel_format(0)
    logger.debug("  - Setting EVM input channel swap ABC->BAC on Port 1...")
    dlpc.set_data_channel_swap(0, 4)
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
        target_hz,
        sequence_utilization=sequence_utilization,
        trig2_frame_zero=trig2_frame_zero,
        entries_count=entries_count,
        per_entry_exposure_us=per_entry_exposure_us,
        dark_time_us=dark_time_us,
        display_dimensions=dlpc.get_display_dimensions(),
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
            f"Source VSYNC is {timing['measured_frame_hz']:.3f} Hz while fixed target is {target_hz} Hz. "
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
    dlpc: "DLPC900",
    target_hz: float = DEFAULT_HZ,
    dual_pixel: bool = False,
    sequence_utilization: float = DEFAULT_SEQUENCE_UTILIZATION,
    trig2_frame_zero: bool = False,
    pre_arm_callback: Callable[[], None] | None = None,
    frame_pump: Callable[[], None] | None = None,
    entries_count: int | None = None,
    per_entry_exposure_us: int | None = None,
    trigger_out_2_rising_delay_us: int = 0,
    dark_time_us: int | None = None,
) -> PreparedSequenceState:
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
