"""DLPC900 LUT timing and trigger-output models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict
import logging
from dmdcontrol.utils import CONFIG

logger = logging.getLogger('LUT')


@dataclass(frozen=True)
class LutEntry:
    pattern_index: int
    exposure_us: int
    clear_after: bool
    bit_depth: int
    led_select: int
    dark_us: int
    trig2_disabled: bool
    bit_position: int
    image_pattern_index: int = 0
    wait_for_trigger: bool = False

    @property
    def bitplane_index(self) -> int:
        """Selected video bit/frame position; kept as a compatibility alias."""
        return self.bit_position


class TriggerOutTiming(TypedDict):
    channel: str
    edge: str
    rising_delay_us: int
    falling_delay_us: int
    pulse_width_us: int


class LutTimingMetadata(TypedDict):
    timing_source: str
    sequence_utilization: float
    frame_period_us: float
    safe_frame_period_us: float
    usable_frame_period_us: float
    safe_margin_us: float
    measured_frame_hz: float | None
    effective_frame_hz: float
    requested_binary_rate_hz: float
    effective_binary_rate_hz: float
    exposure_us: int
    dark_us: int
    total_sequence_us: float
    idle_headroom_us: float
    entries_count: int
    clear_last_after_exposure: NotRequired[bool]
    hold_last_pattern_until_vsync: NotRequired[bool]
    trigger_out_2: NotRequired[TriggerOutTiming]


def build_lut_entries(clear_last_after_exposure: bool = True) -> tuple[list[LutEntry], LutTimingMetadata]:
    """
    Builds the LUT entries for each bitplane

    Args:
        clear_last_after_exposure (bool, optional): wheter to clear the last entry after each exposure. Defaults to True.

    Returns:
        tuple[list[LutEntry], LutTimingMetadata]: list of LutEntry and LutTimingMetadata
    """
    dmd = CONFIG.get('DMD', {})
    target_hz = float(dmd.get('target_hz'))
    bitplanes = dmd.get('bitplanes')
    per_entry_exposure_us = int(dmd.get('exposure_us'))
    min_exposure_us = dmd.get('min_exposure_us')
    safe_margin_us = dmd.get('safe_margin_us')
    dark_time_us = dmd.get('dark_time_us')
    frame_utilization = dmd.get('frame_utilization')
    max_binary_rate_hz = dmd.get('max_binary_rate_hz')
    max_vsync_deviation_ratio = dmd.get('max_vsync_deviation_ratio')

    measured_frame_hz = None
    total_pixels = int(dmd.get('total_pixels_per_line')) * int(dmd.get('total_lines_per_frame'))
    pixel_clock_hz = int(dmd.get('pixel_clock_khz')) * 1000
    if total_pixels > 0 and pixel_clock_hz > 0:
        measured_frame_hz = pixel_clock_hz / total_pixels

    if measured_frame_hz is not None:
        rel_err = abs(measured_frame_hz - target_hz) / target_hz
        if rel_err > max_vsync_deviation_ratio:
            logger.warning(
                "Ignoring unstable measured VSYNC %.3f Hz (target %.3f Hz, deviation %.1f%%). "
                "Using target Hz for LUT timing. Display dims at measurement: total=%sx%s, active=%sx%s, pclk=%skHz",
                measured_frame_hz,
                target_hz,
                rel_err * 100.0,
                dmd.get('total_pixels_per_line'),
                dmd.get('total_lines_per_frame'),
                dmd.get('active_pixels_per_line'),
                dmd.get('active_lines_per_frame'),
                dmd.get('pixel_clock_khz'),
            )
            measured_frame_hz = None

    effective_frame_hz = measured_frame_hz if measured_frame_hz else target_hz
    timing_source = 'measured' if measured_frame_hz else 'target_fallback'
    frame_period_us = 1000000.0 / effective_frame_hz
    safe_frame_period_us = frame_period_us - safe_margin_us
    if safe_frame_period_us <= 0:
        logger.error('Frame period %.2f us is not larger than safety margin %.2f us.', frame_period_us, safe_margin_us)
        raise ValueError(
            f"Frame period {frame_period_us:.2f} us is not larger than safety margin {safe_margin_us:.2f} us."
        )

    usable_frame_period_us = safe_frame_period_us * frame_utilization

    if per_entry_exposure_us < min_exposure_us:
        logger.error('exposure_us (%s) is below the configured minimum (%s).', per_entry_exposure_us, min_exposure_us)
        raise ValueError(f'exposure_us ({per_entry_exposure_us}) is below the configured minimum ({min_exposure_us}).')

    # Fit as many entries as the exposure allows within the frame budget.
    requested_segment_us = per_entry_exposure_us + dark_time_us
    entries_count = int(usable_frame_period_us // requested_segment_us)
    entries_count = max(1, min(bitplanes, entries_count))

    requested_binary_rate_hz = target_hz * entries_count
    if requested_binary_rate_hz > max_binary_rate_hz:
        logger.error('Requested binary rate %.1f Hz exceeds DLP6500 1-bit limit (~%.1f Hz).', requested_binary_rate_hz, max_binary_rate_hz,)
        raise ValueError(f'Requested binary rate {requested_binary_rate_hz:.1f} Hz exceeds DLP6500 1-bit limit (~{max_binary_rate_hz} Hz).')

    effective_binary_rate_hz = effective_frame_hz * entries_count
    if effective_binary_rate_hz > max_binary_rate_hz:
        logger.error('Measured source binary rate %.1f Hz exceeds DLP6500 1-bit limit (~%.1f Hz).', effective_binary_rate_hz, max_binary_rate_hz,)
        raise ValueError(f'Measured source binary rate {effective_binary_rate_hz:.1f} Hz exceeds DLP6500 1-bit limit (~{max_binary_rate_hz} Hz).')

    total_sequence_us = requested_segment_us * entries_count
    if total_sequence_us > usable_frame_period_us:
        logger.error('%d LUT entries at %d us exposure need %.1f us per VSYNC but only %.1f us is usable.', entries_count, per_entry_exposure_us, total_sequence_us, usable_frame_period_us)
        raise ValueError(f'{entries_count} LUT entries at {per_entry_exposure_us} us exposure need {total_sequence_us:.1f} us per VSYNC but only {usable_frame_period_us:.1f} us is usable.')

    idle_headroom_us = frame_period_us - total_sequence_us

    entries: list[LutEntry] = []
    for bit_pos in range(entries_count):
        clear_flag = bool(clear_last_after_exposure and bit_pos == (entries_count - 1))
        entries.append(
            LutEntry(
                pattern_index=bit_pos,
                exposure_us=per_entry_exposure_us,
                clear_after=clear_flag,
                bit_depth=1,
                led_select=7,
                dark_us=dark_time_us,
                trig2_disabled=False,
                bit_position=bit_pos,
                image_pattern_index=0,
                wait_for_trigger=(bit_pos == 0),
            )
        )

    timing: LutTimingMetadata = {
        "timing_source": timing_source,
        "sequence_utilization": frame_utilization,
        "frame_period_us": frame_period_us,
        "safe_frame_period_us": safe_frame_period_us,
        "usable_frame_period_us": usable_frame_period_us,
        "safe_margin_us": safe_margin_us,
        "measured_frame_hz": measured_frame_hz,
        "effective_frame_hz": effective_frame_hz,
        "requested_binary_rate_hz": requested_binary_rate_hz,
        "effective_binary_rate_hz": effective_binary_rate_hz,
        "exposure_us": per_entry_exposure_us,
        "dark_us": dark_time_us,
        "total_sequence_us": total_sequence_us,
        "idle_headroom_us": idle_headroom_us,
        "entries_count": entries_count,
        "clear_last_after_exposure": bool(clear_last_after_exposure),
        "hold_last_pattern_until_vsync": not bool(clear_last_after_exposure),
    }
    return entries, timing


def compute_trigger_out_2_timing() -> TriggerOutTiming:
    pulse_width_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('pulse_width_us'))
    rising_delay_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('rising_delay_us'))
    falling_delay_us = rising_delay_us + pulse_width_us
    
    delay_max_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('delay_max_us'))
    delay_min_us = int(CONFIG.get('DMD', {}).get('trigger_out').get('delay_min_us'))
    max_rising_delay_us = delay_max_us - pulse_width_us
    
    if rising_delay_us < delay_min_us or rising_delay_us > max_rising_delay_us:
        raise ValueError(f'rising_delay_us must be between {delay_min_us} and {max_rising_delay_us}')
    if falling_delay_us < delay_min_us or falling_delay_us > delay_max_us:
        raise ValueError(f'falling_delay_us must be between {delay_min_us} and {delay_max_us}')
    
    return {
        'channel': 'TRIG_OUT_2',
        'edge': 'rising',
        'rising_delay_us': rising_delay_us,
        'falling_delay_us': falling_delay_us,
        'pulse_width_us': pulse_width_us,
    }
