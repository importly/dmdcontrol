from __future__ import annotations

import argparse

from dmdcontrol.camera.local_support_filter import event_noise_filter_metadata
from dmdcontrol.camera.sync_check_runtime import (
    A_COUNT_B_STATIC_TEST,
    _requested_accumulation_window_us,
    _trigger_policy,
    expected_trigger_count,
)
from dmdcontrol.runtime.count_slots import CountSequenceConfig


def _sync_check_test_metadata(args: argparse.Namespace, *, dry_run: bool) -> dict[str, object]:
    if args.test == A_COUNT_B_STATIC_TEST:
        config = CountSequenceConfig.from_args(args)
        metadata = {
            **config.to_metadata(),
            "exposure_us": args.exposure_us,
        }
        if dry_run:
            metadata.update(
                {
                    "accumulation_window_us": _requested_accumulation_window_us(args),
                    "bitplane_count": metadata["count_lut_entries_per_frame"],
                })
        return metadata

    raise ValueError(f"Unsupported sync-check test mode: {args.test}")


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
        "test_b": args.test_b,
        "command": command,
        "number_size_px": args.number_size_px,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "expected_trigger_count": expected_trigger_count(args),
        "paired_startup_leader_vsyncs": args.paired_startup_leader_vsyncs,
        "seq_utilization": args.seq_utilization,
        "trigger_policy": _trigger_policy(args),
        "bias_sensitivity": args.bias_sensitivity,
        "efps": args.efps,
        "polarity_mode": args.polarity_mode,
        "dark_time_us": args.dark_time_us,
        "camera_flush_reads": args.camera_flush_reads,
        "camera_post_trigger_event_batches": args.camera_post_trigger_event_batches,
        "accumulation_cycles": args.requested_accumulation_cycles,
        "accumulation_start_offset_us": args.accumulation_start_offset_us,
        "event_noise_filter": event_noise_filter_metadata(event_filter),
        "save_filtered_events": args.save_filtered_events,
    }
    if dry_run:
        metadata["trigger_mode"] = "per_bitplane"
    metadata.update(_sync_check_test_metadata(args, dry_run=dry_run))
    return metadata
