"""Compatibility exports for DLPC900 lifecycle helpers.

Implementation lives in focused modules:
- `runtime.lut` for LUT entry/timing models.
- `runtime.dlpc_status` for status polling and verification.
- `runtime.video_pattern` for Video Pattern Mode setup and sequencer start.
"""

from __future__ import annotations

from dmdcontrol.runtime.dlpc_status import (
    _format_hw,
    ensure_video_pattern_mode,
    log_board_snapshot,
    verify_runtime_state,
    wait_for_external_lock,
    wait_for_sequencer_running,
)
from dmdcontrol.runtime.lut import (
    DisplayDimensions,
    LutEntry,
    LutTimingMetadata,
    PreparedSequenceState,
    TriggerOutTiming,
    build_lut_entries,
    compute_trigger_out_2_timing,
)
from dmdcontrol.runtime.video_pattern import (
    apply_pattern_sequence,
    configure_dlpc900_for_video_pattern,
    load_pattern_sequence,
    prepare_dlpc900_for_video_pattern,
    start_loaded_pattern_sequence,
    start_loaded_pattern_sequences,
    verify_started_pattern_sequence,
    warn_dark_time_video_pattern_mode,
)

__all__ = [
    "DisplayDimensions",
    "LutEntry",
    "LutTimingMetadata",
    "PreparedSequenceState",
    "TriggerOutTiming",
    "_format_hw",
    "apply_pattern_sequence",
    "build_lut_entries",
    "compute_trigger_out_2_timing",
    "configure_dlpc900_for_video_pattern",
    "ensure_video_pattern_mode",
    "load_pattern_sequence",
    "log_board_snapshot",
    "prepare_dlpc900_for_video_pattern",
    "start_loaded_pattern_sequence",
    "start_loaded_pattern_sequences",
    "verify_runtime_state",
    "verify_started_pattern_sequence",
    "wait_for_external_lock",
    "wait_for_sequencer_running",
    "warn_dark_time_video_pattern_mode",
]
