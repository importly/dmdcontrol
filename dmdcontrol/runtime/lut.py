"""DLPC900 LUT timing and trigger-output models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from dmdcontrol.utils import CONFIG

logger = logging.getLogger('Lut')


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


class PreparedSequenceState(TypedDict):
    entries: list[LutEntry]
    timing: LutTimingMetadata


DisplayDimensions = Mapping[str, Any]


def build_lut_entries(
    trig2_frame_zero: bool = False,
    entries_count: int | None = None,
    per_entry_exposure_us: int | None = None,
    clear_last_after_exposure: bool = True,
    display_dimensions: DisplayDimensions | None = None,
) -> tuple[list[LutEntry], LutTimingMetadata]:
    dmd = CONFIG.get('DMD', {})
    target_hz = float(dmd.get('target_hz'))
    bitplanes = dmd.get('bitplanes')
    min_exposure_us = dmd.get('min_exposure_us')
    safe_margin_us = dmd.get('safe_margin_us')
    dark_time_us = dmd.get('dark_time_us')
    frame_utilization = dmd.get('frame_utilization')
    max_binary_rate_hz = dmd.get('max_binary_rate_hz')
    max_vsync_deviation_ratio = dmd.get('max_vsync_deviation_ratio')
    if per_entry_exposure_us is None:
        per_entry_exposure_us = dmd.get('exposure_us')

    if dark_time_us < 0:
        raise ValueError("dark_time_us must be non-negative")

    measured_frame_hz = None
    dd = display_dimensions
    if (
        dd
        and dd.get("pixel_clock_khz")
        and dd.get("total_pixels_per_line")
        and dd.get("total_lines_per_frame")
    ):
        total_pixels = int(dd["total_pixels_per_line"]) * int(
            dd["total_lines_per_frame"]
        )
        pixel_clock_hz = int(dd["pixel_clock_khz"]) * 1000
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
                dd.get("total_pixels_per_line") if dd else "?",
                dd.get("total_lines_per_frame") if dd else "?",
                dd.get("active_pixels_per_line") if dd else "?",
                dd.get("active_lines_per_frame") if dd else "?",
                dd.get("pixel_clock_khz") if dd else "?",
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
        raise ValueError(
            f"exposure_us ({per_entry_exposure_us}) is below the configured "
            f"minimum ({min_exposure_us})."
        )

    if entries_count is None:
        # Fit as many entries as the exposure allows within the frame budget.
        requested_segment_us = per_entry_exposure_us + dark_time_us
        entries_count = int(usable_frame_period_us // requested_segment_us)
        entries_count = max(1, min(bitplanes, entries_count))
    if entries_count < 1 or entries_count > bitplanes:
        raise ValueError(
            f"entries_count ({entries_count}) must be in [1, {bitplanes}]."
        )

    requested_binary_rate_hz = target_hz * entries_count
    if requested_binary_rate_hz > max_binary_rate_hz:
        raise ValueError(
            f"Requested binary rate {requested_binary_rate_hz:.1f} Hz exceeds "
            f"DLP6500 1-bit limit (~{max_binary_rate_hz} Hz)."
        )

    effective_binary_rate_hz = effective_frame_hz * entries_count
    if effective_binary_rate_hz > max_binary_rate_hz:
        raise ValueError(
            f"Measured source binary rate {effective_binary_rate_hz:.1f} Hz exceeds "
            f"DLP6500 1-bit limit (~{max_binary_rate_hz} Hz)."
        )

    if per_entry_exposure_us is not None:
        if per_entry_exposure_us < CONFIG.get('min_exposure_us', 0):
            raise ValueError(
                f"per_entry_exposure_us ({per_entry_exposure_us}) is below CONFIG.get('min_exposure_us', 0) "
                f"({CONFIG.get('min_exposure_us', 0)})."
            )
        total_needed_us = (per_entry_exposure_us + CONFIG.get('dark_time_us', 0)) * entries_count
        if total_needed_us > usable_frame_period_us:
            raise ValueError(
                f"{entries_count} LUT entries at {per_entry_exposure_us} us exposure need "
                f"{total_needed_us:.1f} us per VSYNC but only {usable_frame_period_us:.1f} us is "
                f"usable (frame_period {frame_period_us:.1f} us, margin {CONFIG.get('safe_margin_us', 0)} us, "
                f"utilization {CONFIG.get('frame_utilization', 1.0)})."
            )
        exposure_us = int(per_entry_exposure_us)
    else:
        segment_budget_us = usable_frame_period_us / entries_count
        if segment_budget_us < min_segment_us:
            max_safe_hz = 1_000_000.0 / (
                (entries_count * min_segment_us / CONFIG.get('frame_utilization', 1.0)) + CONFIG.get('safe_margin_us', 0)
            )
            raise ValueError(
                f"Requested sequence exceeds VSYNC budget: each pattern has {segment_budget_us:.2f} us "
                f"but needs >= {min_segment_us} us (exposure {CONFIG.get('min_exposure_us', 0)} us + dark {CONFIG.get('dark_time_us', 0)} us). "
                f"Reduce source frame rate to <= {max_safe_hz:.2f} Hz."
            )

        segment_us = int(usable_frame_period_us / entries_count)
        exposure_us = segment_us - CONFIG.get('dark_time_us', 0)
        if exposure_us < CONFIG.get('min_exposure_us', 0):
            max_safe_hz = 1_000_000.0 / (
                (entries_count * min_segment_us / CONFIG.get('frame_utilization', 1.0)) + CONFIG.get('safe_margin_us', 0)
            )
            raise ValueError(
                f"Computed exposure {exposure_us} us is below minimum {CONFIG.get('min_exposure_us', 0)} us. "
                f"Reduce source frame rate to <= {max_safe_hz:.2f} Hz."
            )

    total_sequence_us = (exposure_us + CONFIG.get('dark_time_us', 0)) * entries_count
    idle_headroom_us = frame_period_us - total_sequence_us

    entries: list[LutEntry] = []
    for bit_pos in range(entries_count):
        clear_flag = bool(clear_last_after_exposure and bit_pos == (entries_count - 1))
        trig2_disable = (bit_pos != 0) if trig2_frame_zero else False
        entries.append(
            LutEntry(
                pattern_index=bit_pos,
                exposure_us=exposure_us,
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
        "exposure_us": exposure_us,
        "dark_us": dark_time_us,
        "total_sequence_us": total_sequence_us,
        "idle_headroom_us": idle_headroom_us,
        "entries_count": entries_count,
        "clear_last_after_exposure": bool(clear_last_after_exposure),
        "hold_last_pattern_until_vsync": not bool(clear_last_after_exposure),
    }
    return entries, timing


def compute_trigger_out_2_timing(
    rising_delay_us: int = 0,
    pulse_width_us: int = TRIGGER_OUT_PULSE_WIDTH_US,
) -> TriggerOutTiming:
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
            f"{max_rising_delay_us}"
        )
    if not (TRIGGER_OUT_DELAY_MIN_US <= falling_delay_us <= TRIGGER_OUT_DELAY_MAX_US):
        raise ValueError(
            f"falling_delay_us must be between {TRIGGER_OUT_DELAY_MIN_US} and "
            f"{TRIGGER_OUT_DELAY_MAX_US}"
        )
    return {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": rising_delay_us,
        "falling_delay_us": falling_delay_us,
        "pulse_width_us": pulse_width_us,
    }
