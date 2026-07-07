"""DLPC900 status formatting, polling, and runtime health checks."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from dmdcontrol.support.logging import logger

if TYPE_CHECKING:
    from dmdcontrol.hardware.dlpc900 import DLPC900


def _format_hw(hw: int | None) -> str:
    if hw is None:
        return "??"
    # DLPU018J Table 2-21. Bit 5 is reserved (commonly reads 1).
    bits = []
    if hw & 0x01:
        bits.append("init_ok")
    if hw & 0x02:
        bits.append("dmd_compat_err")
    if hw & 0x04:
        bits.append("dmd_reset_err")
    if hw & 0x08:
        bits.append("forced_swap")
    if hw & 0x10:
        bits.append("bit4")
    if hw & 0x20:
        bits.append("bit5_rsvd")
    if hw & 0x40:
        bits.append("ABORT")
    if hw & 0x80:
        bits.append("SEQ_ERR")
    return f"0x{hw:02X}[{'|'.join(bits) if bits else 'clean'}]"


def log_board_snapshot(dlpc: "DLPC900", tag: str) -> None:
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
        if cs["swap_label"] == "BAC":
            logger.debug("  EVM RGB input swap ABC->BAC active; logical RGB maps to DLPC900 pins.")
        elif cs["swap_label"] != "ABC":
            logger.debug(
                f"  Note: non-default channel swap '{cs['swap_label']}' active. Affects RGB->bitplane pin mapping."
            )

    logger.debug("=" * 66)


def wait_for_external_lock(dlpc: "DLPC900", timeout_s: float = 4.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("external_source_locked"):
            return True
        time.sleep(0.2)
    return False


def wait_for_sequencer_running(dlpc: "DLPC900", timeout_s: float = 1.5) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("sequencer_running"):
            return True
        time.sleep(0.1)
    return False


def _bit6_is_cosmetic(dlpc: "DLPC900", hw: int | None) -> bool:
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


def ensure_video_pattern_mode(
    dlpc: "DLPC900",
    retries: int = 3,
    poll_timeout_s: float = 1.2,
) -> bool:
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


def verify_runtime_state(dlpc: "DLPC900") -> bool:
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
