from __future__ import annotations

import argparse

from dmdcontrol.camera.local_support_filter import event_noise_filter_metadata
from dmdcontrol.camera.sync_check_runtime import (
    A_COUNT_B_STATIC_TEST,
    _requested_accumulation_window_us,
    _trigger_policy,
    expected_trigger_count,
)
from dmdcontrol.patterns.paired import count_lut_entries_per_frame


def _sync_check_test_metadata(args: argparse.Namespace, *, dry_run: bool) -> dict[str, object]:
    if args.test == A_COUNT_B_STATIC_TEST:
        metadata = {
            "count_start": args.count_start,
            "count_end": args.count_end,
            "count_slots_per_frame": args.count_slots_per_frame,
            "count_slots_per_frame_mode": getattr(args, "count_slots_per_frame_mode", "explicit"),
            "count_blank_between_frames": getattr(args, "count_blank_between_frames", False),
            "count_lut_entries_per_frame": count_lut_entries_per_frame(
                args.count_slots_per_frame,
                count_blank_between_frames=getattr(args, "count_blank_between_frames", False),
            ),
            "exposure_us": args.exposure_us,
        }
        if dry_run:
            metadata.update(
                {
                    "accumulation_window_us": _requested_accumulation_window_us(args),
                    "bitplane_count": metadata["count_lut_entries_per_frame"],
                })
        return metadata

    metadata = {
        "number_sequence":
        list(args.numbers),
        "numbers_bitplane_order":
        (list(args.numbers_bitplane_order) if args.numbers_bitplane_order is not None else None),
        "exposure_us":
        args.exposure_us,
    }
    if dry_run:
        metadata["bitplane_count"] = len(args.numbers)
    return metadata


def sync_check_metadata(
    args: argparse.Namespace,
    event_filter,
    *,
    dry_run: bool,
    command: list[str],
) -> dict[str,
          object]:
    metadata = {
        "mode": "sync-check",
        "dry_run": dry_run,
        "test": args.test,
        "command": command,
        "number_size_px": args.number_size_px,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "expected_trigger_count": expected_trigger_count(args),
        "seq_utilization": args.seq_utilization,
        "trigger_policy": _trigger_policy(args),
        "bias_sensitivity": args.bias_sensitivity,
        "efps": args.efps,
        "polarity_mode": args.polarity_mode,
        "dark_time_us": args.dark_time_us,
        "camera_open_method": args.camera_open_method,
        "camera_flush_reads": args.camera_flush_reads,
        "camera_post_trigger_event_batches": args.camera_post_trigger_event_batches,
        "camera_stream_rearm": args.camera_stream_rearm,
        "camera_shutdown_streams": args.camera_shutdown_streams,
        "accumulation_cycles": args.requested_accumulation_cycles,
        "accumulation_start_offset_us": args.accumulation_start_offset_us,
        "event_noise_filter": event_noise_filter_metadata(event_filter),
        "save_filtered_events": args.save_filtered_events,
    }
    if dry_run:
        metadata["trigger_mode"] = "per_bitplane"
    metadata.update(_sync_check_test_metadata(args, dry_run=dry_run))
    return metadata
