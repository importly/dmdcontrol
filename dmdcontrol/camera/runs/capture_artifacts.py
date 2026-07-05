from __future__ import annotations

from pathlib import Path

import numpy as np

from dmdcontrol.camera.accumulation import (
    accumulate_events_for_triggers,
    structured_field,
)
from dmdcontrol.camera.local_support_filter import (
    LocalSupportFilterConfig,
    apply_local_support_filter_arrays,
    event_noise_filter_metadata,
)
from dmdcontrol.camera.runs.accumulation_artifacts import (
    _process_accumulation_triggers,
    _record_field,
    _time_range,
    _trigger_timestamps,
    _window_counts,
)
from dmdcontrol.camera.runs.directory import write_json
from dmdcontrol.camera.runs.image_artifacts import _write_accumulation_image_artifacts


def write_capture_artifacts(
    run_directory,
    events,
    triggers,
    resolution,
    window_us,
    polarity_mode="positive",
    window_start_offset_us=0,
    event_noise_filter=None,
    save_filtered_events=False,
    max_accumulation_triggers=None,
    trigger_cycle_length=None,
    accumulation_cycles=None,
    contact_sheet_columns=None,
    startup_leader_trigger_count=0,
):
    _validate_capture_artifact_options(
        max_accumulation_triggers=max_accumulation_triggers,
        trigger_cycle_length=trigger_cycle_length,
        accumulation_cycles=accumulation_cycles,
        startup_leader_trigger_count=startup_leader_trigger_count,
    )
    filter_config = event_noise_filter or LocalSupportFilterConfig(enabled=False)
    filter_config.validate()
    event_sequence = _event_sequence(events)
    event_arrays = _events_to_arrays(event_sequence)
    filtered_arrays, _mask, filter_stats = apply_local_support_filter_arrays(
        event_arrays["x"],
        event_arrays["y"],
        event_arrays["t"],
        event_arrays["p"],
        resolution=resolution,
        config=filter_config,
    )
    accumulation_events = (
        _arrays_to_event_batches(filtered_arrays) if filter_config.enabled else event_sequence)

    accumulation_arrays = filtered_arrays if filter_config.enabled else event_arrays
    trigger_stages = _process_accumulation_triggers(
        triggers,
        accumulation_arrays["t"],
        window_us=int(window_us),
        window_start_offset_us=int(window_start_offset_us),
        max_accumulation_triggers=max_accumulation_triggers,
        trigger_cycle_length=trigger_cycle_length,
        accumulation_cycles=accumulation_cycles,
        startup_leader_trigger_count=startup_leader_trigger_count,
    )
    rising_triggers = trigger_stages.final
    _write_triggers_csv(run_directory.triggers_path, rising_triggers)
    accumulated = accumulate_events_for_triggers(
        accumulation_events,
        rising_triggers,
        resolution=resolution,
        window_us=window_us,
        polarity_mode=polarity_mode,
        window_start_offset_us=window_start_offset_us,
    )
    np.save(run_directory.accumulated_path, accumulated)
    raw_rising_trigger_timestamps = _trigger_timestamps(trigger_stages.raw)
    rising_trigger_timestamps = _trigger_timestamps(rising_triggers)

    artifact_files = _write_accumulation_image_artifacts(
        run_directory,
        accumulated,
        include_filtered=filter_config.enabled,
        contact_sheet_columns=contact_sheet_columns,
    )
    filtered_events_artifact = _write_filtered_events_artifact(
        run_directory,
        filtered_arrays,
        save_filtered_events=save_filtered_events,
    )

    summary = _capture_summary(
        accumulated=accumulated,
        accumulation_arrays=accumulation_arrays,
        artifact_files=artifact_files,
        event_arrays=event_arrays,
        filter_config=filter_config,
        filter_stats=filter_stats,
        filtered_events_artifact=filtered_events_artifact,
        max_accumulation_triggers=max_accumulation_triggers,
        polarity_mode=polarity_mode,
        window_start_offset_us=window_start_offset_us,
        raw_rising_trigger_timestamps=raw_rising_trigger_timestamps,
        resolution=resolution,
        rising_trigger_timestamps=rising_trigger_timestamps,
        rising_triggers=rising_triggers,
        trigger_stages=trigger_stages,
        window_us=window_us,
    )
    write_json(run_directory.summary_path, summary)
    return summary

def _validate_capture_artifact_options(
    *,
    max_accumulation_triggers,
    trigger_cycle_length,
    accumulation_cycles,
    startup_leader_trigger_count,
):
    if max_accumulation_triggers is not None and max_accumulation_triggers <= 0:
        raise ValueError("max_accumulation_triggers must be positive")
    if trigger_cycle_length is not None and trigger_cycle_length <= 0:
        raise ValueError("trigger_cycle_length must be positive")
    if accumulation_cycles is not None and accumulation_cycles <= 0:
        raise ValueError("accumulation_cycles must be positive")
    if startup_leader_trigger_count is not None and startup_leader_trigger_count < 0:
        raise ValueError("startup_leader_trigger_count must be non-negative")

def _event_sequence(events):
    if events is None:
        return []
    if isinstance(events, np.ndarray):
        return [events]
    return list(events)

def _events_to_arrays(events):
    empty = {
        "x": np.array([],
                      dtype=np.int64),
        "y": np.array([],
                      dtype=np.int64),
        "t": np.array([],
                      dtype=np.int64),
        "p": np.array([],
                      dtype=np.bool_),
    }
    if not events:
        return empty
    first = events[0]
    if isinstance(first, np.ndarray):
        batches = [np.asarray(batch) for batch in events if len(batch)]
        if not batches:
            return empty
        event_array = np.concatenate(batches) if len(batches) > 1 else batches[0]
        return {
            "x": structured_field(event_array,
                                  "x").astype(np.int64,
                                              copy=False),
            "y": structured_field(event_array,
                                  "y").astype(np.int64,
                                              copy=False),
            "t": structured_field(event_array,
                                  "timestamp",
                                  "t").astype(np.int64,
                                              copy=False),
            "p": structured_field(event_array,
                                  "polarity",
                                  "p").astype(np.bool_,
                                              copy=False),
        }
    return {
        "x": np.array([_record_field(event,
                                     "x") for event in events],
                      dtype=np.int64),
        "y": np.array([_record_field(event,
                                     "y") for event in events],
                      dtype=np.int64),
        "t": np.array([_record_field(event,
                                     "timestamp") for event in events],
                      dtype=np.int64),
        "p": np.array([_record_field(event,
                                     "polarity") for event in events],
                      dtype=np.bool_),
    }

def _arrays_to_event_batches(arrays):
    event_array = np.zeros(
        len(arrays["t"]),
        dtype=[
            ("timestamp",
             np.int64),
            ("x",
             np.int16),
            ("y",
             np.int16),
            ("polarity",
             np.bool_),
        ],
    )
    event_array["timestamp"] = arrays["t"]
    event_array["x"] = arrays["x"]
    event_array["y"] = arrays["y"]
    event_array["polarity"] = arrays["p"]
    return [event_array] if len(event_array) else []

def _write_event_npz(path, arrays):
    np.savez(
        path,
        x=arrays["x"],
        y=arrays["y"],
        t=arrays["t"],
        p=arrays["p"],
    )

def _write_triggers_csv(path, triggers):
    lines = ["index,timestamp,edge"]
    for index, trigger in enumerate(triggers):
        timestamp = _record_field(trigger, "timestamp")
        edge = _record_field(trigger, "edge", default="rising")
        lines.append(f"{index},{int(timestamp)},{edge}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

def _write_filtered_events_artifact(run_directory, filtered_arrays, *, save_filtered_events):
    if not save_filtered_events:
        return None
    artifact = "filtered_events.npz"
    _write_event_npz(run_directory.path / artifact, filtered_arrays)
    return artifact

def _capture_summary(
    *,
    accumulated,
    accumulation_arrays,
    artifact_files,
    event_arrays,
    filter_config,
    filter_stats,
    filtered_events_artifact,
    max_accumulation_triggers,
    polarity_mode,
    window_start_offset_us,
    raw_rising_trigger_timestamps,
    resolution,
    rising_trigger_timestamps,
    rising_triggers,
    trigger_stages,
    window_us,
):
    summary = {
        "actual_trigger_count":
        len(rising_triggers),
        "aligned_rising_trigger_count":
        len(trigger_stages.aligned),
        "selected_rising_trigger_count":
        len(trigger_stages.selected),
        "raw_rising_trigger_count":
        len(trigger_stages.raw),
        "max_accumulation_triggers":
        max_accumulation_triggers,
        "accumulation_trigger_limited":
        len(rising_triggers) < len(trigger_stages.raw),
        "trigger_alignment":
        trigger_stages.alignment_metadata,
        "startup_leader_skip":
        trigger_stages.leader_skip_metadata,
        "trigger_cycle_limit":
        trigger_stages.cycle_limit_metadata,
        "event_count":
        filter_stats.raw_events,
        "accumulation_event_count":
        (filter_stats.filtered_events if filter_config.enabled else filter_stats.raw_events),
        "accumulation_event_source":
        "filtered" if filter_config.enabled else "raw",
        "event_noise_filter":
        event_noise_filter_metadata(filter_config,
                                    filter_stats),
        "window_us":
        int(window_us),
        "window_start_offset_us":
        int(window_start_offset_us),
        "polarity_mode":
        polarity_mode,
        "resolution": [int(resolution[0]),
                       int(resolution[1])],
        "accumulated_shape":
        list(accumulated.shape),
        "event_time_range_us":
        _time_range(event_arrays["t"]),
        "accumulation_event_time_range_us":
        _time_range(accumulation_arrays["t"]),
        "raw_rising_trigger_time_range_us":
        _time_range(raw_rising_trigger_timestamps),
        "rising_trigger_time_range_us":
        _time_range(rising_trigger_timestamps),
        "events_per_accumulation_window":
        _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_start_offset_us),
            int(window_us),
        ),
        "events_per_pre_trigger_window":
        _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_start_offset_us) - int(window_us),
            int(window_us),
        ),
        "events_per_post_window":
        _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_start_offset_us) + int(window_us),
            int(window_us),
        ),
        "accumulated_nonzero_pixels": [int(np.count_nonzero(frame)) for frame in accumulated],
        "accumulated_abs_sums": [float(np.sum(np.abs(frame))) for frame in accumulated],
        "frame_artifacts":
        artifact_files["frame_artifacts"],
    }
    if filtered_events_artifact is not None:
        summary["filtered_events_artifact"] = filtered_events_artifact
    if artifact_files["filtered_frame_artifacts"]:
        summary["filtered_frame_artifacts"] = artifact_files["filtered_frame_artifacts"]
    if artifact_files["filtered_contact_sheet_artifact"] is not None:
        summary["filtered_contact_sheet_artifact"] = artifact_files[
            "filtered_contact_sheet_artifact"]
    return summary
