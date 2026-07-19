from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from dmdcontrol.camera.accumulation import filter_rising_triggers
from dmdcontrol.camera.record_fields import as_int


@dataclass(frozen=True)
class _AccumulationTriggerStages:
    raw: list
    aligned: list
    selected: list
    final: list
    alignment_metadata: dict
    leader_skip_metadata: dict
    cycle_limit_metadata: dict

def _trigger_timestamps(triggers):
    return np.array(
        [
            as_int(_record_field(trigger, "timestamp"), name="timestamp")
            for trigger in triggers
        ],
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
    startup_leader_trigger_count=0,):
    raw = filter_rising_triggers(triggers)
    semantic_input, leader_skip_metadata = _skip_startup_leader_triggers(
        raw,
        startup_leader_trigger_count,
    )
    aligned, alignment_metadata = _align_triggers_to_event_range(
        semantic_input,
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
        selected[:max_accumulation_triggers] if max_accumulation_triggers is not None else selected)
    return _AccumulationTriggerStages(
        raw=raw,
        aligned=aligned,
        selected=selected,
        final=final,
        alignment_metadata=alignment_metadata,
        leader_skip_metadata=leader_skip_metadata,
        cycle_limit_metadata=cycle_limit_metadata,
    )

def _skip_startup_leader_triggers(triggers, startup_leader_trigger_count):
    requested = int(startup_leader_trigger_count or 0)
    skipped = min(max(0, requested), len(triggers))
    remaining = list(triggers[skipped:])
    metadata = {
        "requested_trigger_count": requested,
        "skipped_trigger_count": skipped,
        "input_trigger_count": len(triggers),
        "remaining_trigger_count": len(remaining),
    }
    return remaining, metadata

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
        trigger for trigger, should_keep in zip(triggers, keep, strict=False) if bool(should_keep)]
    metadata.update(
        {
            "aligned_trigger_count": len(aligned),
            "dropped_before_event_count": int(np.count_nonzero(dropped_before)),
            "dropped_after_event_count": int(np.count_nonzero(dropped_after)),
        })
    return aligned, metadata

def _limit_trigger_cycles(
    triggers,
    *,
    trigger_cycle_length,
    accumulation_cycles,):
    available_full_cycles = (
        len(triggers) // int(trigger_cycle_length) if trigger_cycle_length is not None else 0)
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

    metadata.update(
        {
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
