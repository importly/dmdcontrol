from __future__ import annotations

import json
import math
import struct
import zlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

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
        event_noise_filter=None,
        save_filtered_events=False,
        max_accumulation_triggers=None,
):
    if max_accumulation_triggers is not None and max_accumulation_triggers <= 0:
        raise ValueError("max_accumulation_triggers must be positive")
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

    raw_rising_triggers = filter_rising_triggers(triggers)
    rising_triggers = (
        raw_rising_triggers[:max_accumulation_triggers]
        if max_accumulation_triggers is not None
        else raw_rising_triggers
    )
    _write_triggers_csv(run_directory.triggers_path, rising_triggers)
    accumulated = accumulate_events_for_triggers(
        accumulation_events,
        rising_triggers,
        resolution=resolution,
        window_us=window_us,
        polarity_mode=polarity_mode,
    )
    np.save(run_directory.accumulated_path, accumulated)
    accumulation_arrays = filtered_arrays if filter_config.enabled else event_arrays
    rising_trigger_timestamps = _trigger_timestamps(rising_triggers)

    frame_artifacts = []
    filtered_frame_artifacts = []
    for index, frame in enumerate(accumulated, start=1):
        frame_path = run_directory.path / f"accumulated_{index:03d}.png"
        _write_grayscale_png(frame_path, frame)
        frame_artifacts.append(frame_path.name)
        if filter_config.enabled:
            filtered_frame_path = run_directory.path / f"filtered_accumulated_{index:03d}.png"
            _write_grayscale_png(filtered_frame_path, frame)
            filtered_frame_artifacts.append(filtered_frame_path.name)
    contact_sheet = _contact_sheet(accumulated)
    _write_grayscale_png(run_directory.contact_sheet_path, contact_sheet)

    filtered_contact_sheet_artifact = None
    if filter_config.enabled:
        filtered_contact_sheet_artifact = "filtered_contact_sheet.png"
        _write_grayscale_png(run_directory.path / filtered_contact_sheet_artifact, contact_sheet)

    filtered_events_artifact = None
    if save_filtered_events:
        filtered_events_artifact = "filtered_events.npz"
        _write_event_npz(run_directory.path / filtered_events_artifact, filtered_arrays)

    summary = {
        "actual_trigger_count": len(rising_triggers),
        "raw_rising_trigger_count": len(raw_rising_triggers),
        "max_accumulation_triggers": max_accumulation_triggers,
        "accumulation_trigger_limited": len(rising_triggers) < len(raw_rising_triggers),
        "event_count": filter_stats.raw_events,
        "accumulation_event_count": (
            filter_stats.filtered_events if filter_config.enabled else filter_stats.raw_events
        ),
        "accumulation_event_source": "filtered" if filter_config.enabled else "raw",
        "event_noise_filter": event_noise_filter_metadata(filter_config, filter_stats),
        "window_us": int(window_us),
        "polarity_mode": polarity_mode,
        "resolution": [int(resolution[0]), int(resolution[1])],
        "accumulated_shape": list(accumulated.shape),
        "event_time_range_us": _time_range(event_arrays["t"]),
        "accumulation_event_time_range_us": _time_range(accumulation_arrays["t"]),
        "rising_trigger_time_range_us": _time_range(rising_trigger_timestamps),
        "events_per_accumulation_window": _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps,
            int(window_us),
        ),
        "events_per_pre_trigger_window": _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps - int(window_us),
            int(window_us),
        ),
        "events_per_post_window": _window_counts(
            accumulation_arrays["t"],
            rising_trigger_timestamps + int(window_us),
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
        "frame_artifacts": frame_artifacts,
    }
    if filtered_events_artifact is not None:
        summary["filtered_events_artifact"] = filtered_events_artifact
    if filtered_frame_artifacts:
        summary["filtered_frame_artifacts"] = filtered_frame_artifacts
    if filtered_contact_sheet_artifact is not None:
        summary["filtered_contact_sheet_artifact"] = filtered_contact_sheet_artifact
    write_json(run_directory.summary_path, summary)
    return summary


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


def _contact_sheet(frames):
    if len(frames) == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    normalized = [_normalize_grayscale(frame) for frame in frames]
    frame_h, frame_w = normalized[0].shape
    cols = max(1, math.ceil(math.sqrt(len(normalized))))
    rows = math.ceil(len(normalized) / cols)
    sheet = np.zeros((rows * frame_h, cols * frame_w), dtype=np.uint8)
    for index, frame in enumerate(normalized):
        row = index // cols
        col = index % cols
        y0 = row * frame_h
        x0 = col * frame_w
        sheet[y0:y0 + frame_h, x0:x0 + frame_w] = frame
    return sheet


def _normalize_grayscale(frame):
    array = np.asarray(frame, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("frame must be a 2D array")
    if array.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    minimum = float(np.min(array))
    maximum = float(np.max(array))
    if maximum <= minimum:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = (array - minimum) * (255.0 / (maximum - minimum))
    return np.clip(scaled, 0, 255).astype(np.uint8)


def _write_grayscale_png(path, frame):
    image = _normalize_grayscale(frame)
    height, width = image.shape
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
    payload += _png_chunk(b"IDAT", zlib.compress(raw))
    payload += _png_chunk(b"IEND", b"")
    Path(path).write_bytes(payload)


def _png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )
