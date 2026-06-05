from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from dmdcontrol.camera.accumulation import accumulate_events_for_triggers, filter_rising_triggers
from dmdcontrol.camera.local_support_filter import (
    LocalSupportFilterConfig,
    apply_local_support_filter_arrays,
    event_noise_filter_metadata,
)


@dataclass(frozen=True)
class CameraRunDirectory:
    path: Path
    raw_recording_path: Path
    metadata_path: Path
    command_path: Path
    log_path: Path
    triggers_path: Path
    accumulated_path: Path
    timing_path: Path
    contact_sheet_path: Path
    summary_path: Path


@dataclass(frozen=True)
class _AccumulationTriggerStages:
    raw: list
    aligned: list
    selected: list
    final: list
    alignment_metadata: dict
    cycle_limit_metadata: dict


def default_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def create_run_directory(mode, output_root=None, timestamp=None):
    root = Path(output_root) if output_root is not None else Path("runs") / "camera"
    run_path = root / f"{timestamp or default_timestamp()}-{mode}"
    run_path.mkdir(parents=True, exist_ok=False)
    return CameraRunDirectory(
        path=run_path,
        raw_recording_path=run_path / "raw.aedat4",
        metadata_path=run_path / "metadata.json",
        command_path=run_path / "command.txt",
        log_path=run_path / "run.log",
        triggers_path=run_path / "triggers.csv",
        accumulated_path=run_path / "accumulated.npy",
        timing_path=run_path / "timing.json",
        contact_sheet_path=run_path / "contact_sheet.png",
        summary_path=run_path / "summary.json",
    )


def write_json(path, payload):
    output_path = Path(path)
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def write_run_metadata(run_directory, metadata, artifacts=None):
    payload = dict(metadata)
    payload["run_directory"] = str(run_directory.path)
    payload["metadata_path"] = str(run_directory.metadata_path)
    payload["artifacts"] = list(artifacts or [])
    write_json(run_directory.metadata_path, payload)
    return payload


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
):
    _validate_capture_artifact_options(
        max_accumulation_triggers=max_accumulation_triggers,
        trigger_cycle_length=trigger_cycle_length,
        accumulation_cycles=accumulation_cycles,
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
        _arrays_to_event_batches(filtered_arrays)
        if filter_config.enabled
        else event_sequence
    )

    accumulation_arrays = filtered_arrays if filter_config.enabled else event_arrays
    trigger_stages = _process_accumulation_triggers(
        triggers,
        accumulation_arrays["t"],
        window_us=int(window_us),
        window_start_offset_us=int(window_start_offset_us),
        max_accumulation_triggers=max_accumulation_triggers,
        trigger_cycle_length=trigger_cycle_length,
        accumulation_cycles=accumulation_cycles,
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
):
    if max_accumulation_triggers is not None and max_accumulation_triggers <= 0:
        raise ValueError("max_accumulation_triggers must be positive")
    if trigger_cycle_length is not None and trigger_cycle_length <= 0:
        raise ValueError("trigger_cycle_length must be positive")
    if accumulation_cycles is not None and accumulation_cycles <= 0:
        raise ValueError("accumulation_cycles must be positive")


def _event_sequence(events):
    if events is None:
        return []
    if isinstance(events, np.ndarray):
        return [events]
    return list(events)


def _events_to_arrays(events):
    empty = {
        "x": np.array([], dtype=np.int64),
        "y": np.array([], dtype=np.int64),
        "t": np.array([], dtype=np.int64),
        "p": np.array([], dtype=np.bool_),
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
            "x": _structured_field(event_array, "x").astype(np.int64, copy=False),
            "y": _structured_field(event_array, "y").astype(np.int64, copy=False),
            "t": _structured_field(event_array, "timestamp", "t").astype(np.int64, copy=False),
            "p": _structured_field(event_array, "polarity", "p").astype(np.bool_, copy=False),
        }
    return {
        "x": np.array([_record_field(event, "x") for event in events], dtype=np.int64),
        "y": np.array([_record_field(event, "y") for event in events], dtype=np.int64),
        "t": np.array([_record_field(event, "timestamp") for event in events], dtype=np.int64),
        "p": np.array([_record_field(event, "polarity") for event in events], dtype=np.bool_),
    }


def _structured_field(event_array, *names):
    field_names = event_array.dtype.names or ()
    for name in names:
        if name in field_names:
            return event_array[name]
    raise ValueError(f"event array missing required field: one of {names!r}")


def _arrays_to_event_batches(arrays):
    event_array = np.zeros(
        len(arrays["t"]),
        dtype=[
            ("timestamp", np.int64),
            ("x", np.int16),
            ("y", np.int16),
            ("polarity", np.bool_),
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


def _write_accumulation_image_artifacts(
        run_directory,
        accumulated,
        *,
        include_filtered,
        contact_sheet_columns=None,
):
    frame_artifacts = []
    filtered_frame_artifacts = []
    scale_max = _grayscale_scale_max(accumulated)
    for index, frame in enumerate(accumulated, start=1):
        frame_path = run_directory.path / f"accumulated_{index:03d}.png"
        _write_grayscale_png(frame_path, frame, scale_max=scale_max)
        frame_artifacts.append(frame_path.name)
        if include_filtered:
            filtered_frame_path = run_directory.path / f"filtered_accumulated_{index:03d}.png"
            _write_grayscale_png(filtered_frame_path, frame, scale_max=scale_max)
            filtered_frame_artifacts.append(filtered_frame_path.name)

    contact_sheet = _contact_sheet(
        accumulated,
        scale_max=scale_max,
        cols=contact_sheet_columns,
    )
    _write_grayscale_png(run_directory.contact_sheet_path, contact_sheet, scale_max=255)

    filtered_contact_sheet_artifact = None
    if include_filtered:
        filtered_contact_sheet_artifact = "filtered_contact_sheet.png"
        _write_grayscale_png(
            run_directory.path / filtered_contact_sheet_artifact,
            contact_sheet,
            scale_max=255,
        )

    return {
        "frame_artifacts": frame_artifacts,
        "filtered_frame_artifacts": filtered_frame_artifacts,
        "filtered_contact_sheet_artifact": filtered_contact_sheet_artifact,
    }


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
        "actual_trigger_count": len(rising_triggers),
        "aligned_rising_trigger_count": len(trigger_stages.aligned),
        "selected_rising_trigger_count": len(trigger_stages.selected),
        "raw_rising_trigger_count": len(trigger_stages.raw),
        "max_accumulation_triggers": max_accumulation_triggers,
        "accumulation_trigger_limited": len(rising_triggers) < len(trigger_stages.raw),
        "trigger_alignment": trigger_stages.alignment_metadata,
        "trigger_cycle_limit": trigger_stages.cycle_limit_metadata,
        "event_count": filter_stats.raw_events,
        "accumulation_event_count": (
            filter_stats.filtered_events if filter_config.enabled else filter_stats.raw_events
        ),
        "accumulation_event_source": "filtered" if filter_config.enabled else "raw",
        "event_noise_filter": event_noise_filter_metadata(filter_config, filter_stats),
        "window_us": int(window_us),
        "window_start_offset_us": int(window_start_offset_us),
        "polarity_mode": polarity_mode,
        "resolution": [int(resolution[0]), int(resolution[1])],
        "accumulated_shape": list(accumulated.shape),
        "event_time_range_us": _time_range(event_arrays["t"]),
        "accumulation_event_time_range_us": _time_range(accumulation_arrays["t"]),
        "raw_rising_trigger_time_range_us": _time_range(raw_rising_trigger_timestamps),
        "rising_trigger_time_range_us": _time_range(rising_trigger_timestamps),
        "events_per_accumulation_window": _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_start_offset_us),
            int(window_us),
        ),
        "events_per_pre_trigger_window": _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_start_offset_us) - int(window_us),
            int(window_us),
        ),
        "events_per_post_window": _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_start_offset_us) + int(window_us),
            int(window_us),
        ),
        "accumulated_nonzero_pixels": [
            int(np.count_nonzero(frame))
            for frame in accumulated
        ],
        "accumulated_abs_sums": [
            float(np.sum(np.abs(frame)))
            for frame in accumulated
        ],
        "frame_artifacts": artifact_files["frame_artifacts"],
    }
    if filtered_events_artifact is not None:
        summary["filtered_events_artifact"] = filtered_events_artifact
    if artifact_files["filtered_frame_artifacts"]:
        summary["filtered_frame_artifacts"] = artifact_files["filtered_frame_artifacts"]
    if artifact_files["filtered_contact_sheet_artifact"] is not None:
        summary["filtered_contact_sheet_artifact"] = artifact_files["filtered_contact_sheet_artifact"]
    return summary


def _trigger_timestamps(triggers):
    return np.array(
        [int(_record_field(trigger, "timestamp")) for trigger in triggers],
        dtype=np.int64,
    )


def _time_range(values):
    array = np.asarray(values, dtype=np.int64)
    if len(array) == 0:
        return None
    return [int(np.min(array)), int(np.max(array))]


def _process_accumulation_triggers(
        triggers,
        event_timestamps,
        *,
        window_us,
        window_start_offset_us,
        max_accumulation_triggers,
        trigger_cycle_length,
        accumulation_cycles,
):
    raw = filter_rising_triggers(triggers)
    aligned, alignment_metadata = _align_triggers_to_event_range(
        raw,
        event_timestamps,
        int(window_us),
        int(window_start_offset_us),
    )
    selected, cycle_limit_metadata = _limit_trigger_cycles(
        aligned,
        trigger_cycle_length=trigger_cycle_length,
        accumulation_cycles=accumulation_cycles,
    )
    final = (
        selected[:max_accumulation_triggers]
        if max_accumulation_triggers is not None
        else selected
    )
    return _AccumulationTriggerStages(
        raw=raw,
        aligned=aligned,
        selected=selected,
        final=final,
        alignment_metadata=alignment_metadata,
        cycle_limit_metadata=cycle_limit_metadata,
    )


def _align_triggers_to_event_range(triggers, event_timestamps, window_us, window_start_offset_us=0):
    trigger_timestamps = _trigger_timestamps(triggers)
    event_time_range = _time_range(event_timestamps)
    metadata = {
        "mode": "event_overlap",
        "event_time_range_us": event_time_range,
        "window_us": int(window_us),
        "window_start_offset_us": int(window_start_offset_us),
        "input_trigger_count": len(triggers),
        "aligned_trigger_count": len(triggers),
        "dropped_before_event_count": 0,
        "dropped_after_event_count": 0,
    }
    if len(triggers) == 0 or event_time_range is None or window_us <= 0:
        return list(triggers), metadata

    event_start, event_end = event_time_range
    window_us = int(window_us)
    window_starts = trigger_timestamps + int(window_start_offset_us)
    keep = (window_starts + window_us > event_start) & (window_starts <= event_end)
    dropped_before = window_starts + window_us <= event_start
    dropped_after = window_starts > event_end
    aligned = [
        trigger
        for trigger, should_keep in zip(triggers, keep, strict=False)
        if bool(should_keep)
    ]
    metadata.update({
        "aligned_trigger_count": len(aligned),
        "dropped_before_event_count": int(np.count_nonzero(dropped_before)),
        "dropped_after_event_count": int(np.count_nonzero(dropped_after)),
    })
    return aligned, metadata


def _limit_trigger_cycles(
        triggers,
        *,
        trigger_cycle_length,
        accumulation_cycles,
):
    available_full_cycles = (
        len(triggers) // int(trigger_cycle_length)
        if trigger_cycle_length is not None
        else 0
    )
    metadata = {
        "cycle_length": trigger_cycle_length,
        "requested_cycles": accumulation_cycles,
        "available_full_cycles": available_full_cycles,
        "selected_cycle_indices": [],
        "selected_trigger_count": len(triggers),
    }
    if accumulation_cycles is None or trigger_cycle_length is None:
        return list(triggers), metadata
    if len(triggers) == 0 or available_full_cycles == 0:
        metadata["selected_trigger_count"] = 0
        return [], metadata

    cycle_length = int(trigger_cycle_length)
    requested_cycles = min(int(accumulation_cycles), available_full_cycles)
    selected_cycle_indices = list(range(requested_cycles))

    selected = []
    for cycle_index in selected_cycle_indices:
        start = cycle_index * cycle_length
        selected.extend(triggers[start:start + cycle_length])

    metadata.update({
        "selected_cycle_indices": selected_cycle_indices,
        "selected_trigger_count": len(selected),
    })
    return selected, metadata


def _window_counts(timestamps, starts, window_us):
    start_array = np.asarray(starts, dtype=np.int64)
    if len(start_array) == 0:
        return []
    if window_us <= 0:
        return [0 for _ in start_array]
    time_array = np.sort(np.asarray(timestamps, dtype=np.int64))
    if len(time_array) == 0:
        return [0 for _ in start_array]
    end_array = start_array + int(window_us)
    left = np.searchsorted(time_array, start_array, side="left")
    right = np.searchsorted(time_array, end_array, side="left")
    return (right - left).astype(int).tolist()


def _record_field(record, name, default=None):
    if hasattr(record, name):
        value = getattr(record, name)
        return value() if callable(value) else value
    if isinstance(record, dict):
        return record.get(name, default)
    if default is not None:
        return default
    raise AttributeError(f"{record!r} has no {name!r} field")


def _contact_sheet(frames, *, scale_max=None, cols=None):
    if len(frames) == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    normalized = [_normalize_grayscale(frame, scale_max=scale_max) for frame in frames]
    frame_h, frame_w = normalized[0].shape
    cols = max(1, int(cols)) if cols is not None else max(1, math.ceil(math.sqrt(len(normalized))))
    rows = math.ceil(len(normalized) / cols)
    sheet = np.zeros((rows * frame_h, cols * frame_w), dtype=np.uint8)
    for index, frame in enumerate(normalized):
        row = index // cols
        col = index % cols
        y0 = row * frame_h
        x0 = col * frame_w
        sheet[y0:y0 + frame_h, x0:x0 + frame_w] = frame
    return sheet


def _grayscale_scale_max(frames):
    array = np.asarray(frames, dtype=np.float32)
    if array.size == 0:
        return 0.0
    return float(np.max(np.abs(array)))


def _normalize_grayscale(frame, *, scale_max=None):
    array = np.asarray(frame, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("frame must be a 2D array")
    if array.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    magnitude = np.abs(array)
    maximum = float(scale_max) if scale_max is not None else float(np.max(magnitude))
    if maximum <= 0:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = np.log1p(magnitude) * (255.0 / np.log1p(maximum))
    return np.rint(np.clip(scaled, 0, 255)).astype(np.uint8)


def _write_grayscale_png(path, frame, *, scale_max=None):
    image = _normalize_grayscale(frame, scale_max=scale_max)
    Image.fromarray(np.ascontiguousarray(image)).save(Path(path), format="PNG")
