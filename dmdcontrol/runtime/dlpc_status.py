"""DLPC900 status formatting, polling, and runtime health checks."""

from __future__ import annotations
import time
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dmdcontrol.dmd import DLPC900


logger = logging.getLogger('DLPC900_status')


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



def wait_for_external_lock(dlpc: DLPC900, timeout_s: float = 4.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("external_source_locked"):
            return True
        time.sleep(0.2)
    return False


def wait_for_stable_external_lock(
    dlpc: DLPC900,
    *,
    timeout_s: float,
    stable_for_s: float = 0.25,
    poll_interval_s: float = 0.05,
    required_mode: int | None = None,
) -> bool:
    """Return once the external video source remains healthy for a bounded interval."""
    if timeout_s < 0:
        raise ValueError("timeout_s must be non-negative")
    if stable_for_s < 0:
        raise ValueError("stable_for_s must be non-negative")
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be positive")

    deadline = time.monotonic() + timeout_s
    stable_since: float | None = None
    while True:
        now = time.monotonic()
        if now > deadline:
            return False

        main_status = dlpc.get_main_status() or {}
        mode_matches = True
        if required_mode is not None:
            mode, _ = dlpc.get_display_mode()
            mode_matches = mode == required_mode
        source_ready = bool(
            main_status.get("external_source_locked")
            and main_status.get("port1_syncs_valid")
            and not main_status.get("video_frozen")
            and mode_matches
        )

        if source_ready:
            if stable_since is None:
                stable_since = now
            if now - stable_since >= stable_for_s:
                return True
        else:
            stable_since = None

        remaining_s = deadline - now
        if remaining_s <= 0:
            return False
        time.sleep(min(poll_interval_s, remaining_s))


def wait_for_sequencer_running(dlpc: DLPC900, timeout_s: float = 1.5) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("sequencer_running"):
            return True
        time.sleep(0.1)
    return False


def _bit6_is_cosmetic(dlpc: DLPC900, hw: int | None) -> bool:
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
    dlpc: DLPC900,
    retries: int = 3,
    poll_timeout_s: float = 1.2,) -> bool:
    mode, _ = dlpc.get_display_mode()
    if mode == 2:
        return True

    for attempt in range(1, retries + 1):
        logger.warning('Mode readback shows %s, not 2! Retrying mode transition (%d/%d)...', mode, attempt, retries)
        dlpc.set_display_mode(0x02)

        time.sleep(0.35)
        deadline = time.time() + poll_timeout_s
        while time.time() < deadline:
            mode, _ = dlpc.get_display_mode()
            if mode == 2:
                logger.debug('  - After retry %d, mode readback: %s', attempt, mode)
                return True
            time.sleep(0.1)

        logger.debug('  - After retry %d, mode readback: %s', attempt, mode)

    return False

