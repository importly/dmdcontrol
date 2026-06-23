from __future__ import annotations

import numpy as np


class BoundedArtifactBuffer:

    def __init__(self, max_rising_triggers: int | None, window_us: int):
        self.max_rising_triggers = max_rising_triggers
        self.window_us = max(0, int(window_us))
        self.events = []
        self.triggers = []
        self.raw_rising_triggers = 0
        self.cutoff_us = None
        self.truncated = False

    def append_events(self, batch) -> None:
        records = _event_records_from_batch(batch)
        if _record_count(records) == 0:
            return
        filtered = self._filter_events(records)
        if _record_count(filtered) == 0:
            return
        if isinstance(filtered, np.ndarray):
            self.events.append(filtered)
        else:
            self.events.extend(filtered)

    def append_triggers(self, batch) -> None:
        if batch is None:
            return
        for trigger in list(batch):
            is_rising = _trigger_edge(trigger) == "rising"
            if is_rising:
                self.raw_rising_triggers += 1
            if self.max_rising_triggers is not None and self.raw_rising_triggers > self.max_rising_triggers:
                self.truncated = True
                continue
            self.triggers.append(trigger)
            if (is_rising and self.max_rising_triggers is not None
                    and self.raw_rising_triggers == self.max_rising_triggers):
                self.cutoff_us = _record_timestamp(trigger) + self.window_us
                self._prune_events_to_cutoff()

    def to_metadata(self) -> dict:
        return {
            "max_accumulation_triggers": self.max_rising_triggers,
            "retained_trigger_records": len(self.triggers),
            "raw_rising_triggers_seen": self.raw_rising_triggers,
            "artifact_capture_truncated": self.truncated,
            "event_cutoff_us": self.cutoff_us,
        }

    def _filter_events(self, records):
        if self.cutoff_us is None:
            return records
        return _filter_events_before(records, self.cutoff_us)

    def _prune_events_to_cutoff(self) -> None:
        if self.cutoff_us is None:
            return
        pruned = []
        for records in self.events:
            if isinstance(records, np.ndarray):
                filtered = _filter_events_before(records, self.cutoff_us)
                if _record_count(filtered) != 0:
                    pruned.append(filtered)
            elif _record_timestamp(records) < self.cutoff_us:
                pruned.append(records)
        self.events = pruned


def _event_records_from_batch(batch):
    if batch is None:
        return []
    if hasattr(batch, "numpy"):
        return np.array(batch.numpy(), copy=True)
    if isinstance(batch, np.ndarray):
        return np.array(batch, copy=True)
    try:
        return list(batch)
    except TypeError:
        return [batch]


def _filter_events_before(records, cutoff_us):
    if isinstance(records, np.ndarray):
        timestamp_field = _timestamp_field_name(records)
        return records[records[timestamp_field] < cutoff_us]
    return [record for record in records if _record_timestamp(record) < cutoff_us]


def _timestamp_field_name(records):
    field_names = records.dtype.names or ()
    if "timestamp" in field_names:
        return "timestamp"
    if "t" in field_names:
        return "t"
    raise ValueError("event array missing timestamp field")


def _record_count(records) -> int:
    try:
        return len(records)
    except TypeError:
        return 0


def _trigger_edge(record) -> str:
    return str(_record_field(record, "edge", default="rising")).lower()


def _record_timestamp(record) -> int:
    return int(_record_field(record, "timestamp"))


def _record_field(record, name, default=None):
    if hasattr(record, name):
        value = getattr(record, name)
        return value() if callable(value) else value
    if isinstance(record, dict):
        return record.get(name, default)
    if isinstance(record, np.void) and record.dtype.names and name in record.dtype.names:
        return record[name]
    if default is not None:
        return default
    raise AttributeError(f"{record!r} has no {name!r} field")
