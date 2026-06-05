from __future__ import annotations

from dataclasses import dataclass

import numpy as np


_MISSING = object()


@dataclass(frozen=True)
class TriggerRecord:
    timestamp: int
    edge: str = "rising"


@dataclass(frozen=True)
class EventRecord:
    timestamp: int
    x: int
    y: int
    polarity: bool


def filter_rising_triggers(triggers):
    return [trigger for trigger in triggers if _trigger_edge(trigger) == "rising"]


# becoming suspect of this function now
def accumulate_events_for_triggers(
    events,
    triggers,
    resolution,
    window_us,
    polarity_mode,
    window_start_offset_us=0,
):
    if window_us < 0:
        raise ValueError("window_us must be non-negative")
    window_start_offset_us = int(window_start_offset_us)
    width, height = resolution
    if width <= 0 or height <= 0:
        raise ValueError("resolution must contain positive width and height")
    if polarity_mode not in {"positive", "signed", "ignore"}:
        raise ValueError("polarity_mode must be one of: positive, signed, ignore")

    rising_triggers = filter_rising_triggers(triggers)
    frames = np.zeros((len(rising_triggers), height, width), dtype=np.float32)

    if not events:
        return frames

    if isinstance(events[0], np.ndarray):
        ev = np.concatenate(events)
    else:
        ev = np.zeros(len(events), dtype=[('timestamp', np.int64), ('x', np.int16), ('y', np.int16), ('polarity', np.bool_)])
        for i, e in enumerate(events):
            ev['timestamp'][i] = _timestamp(e)
            ev['x'][i] = _field(e, 'x')
            ev['y'][i] = _field(e, 'y')
            ev['polarity'][i] = _field(e, 'polarity')

    ev_t = ev['timestamp']
    ev_x = ev['x'].astype(np.int64)
    ev_y = ev['y'].astype(np.int64)
    ev_p = ev['polarity']

    if polarity_mode == "positive":
        ev_v = ev_p.astype(np.float32)
    elif polarity_mode == "signed":
        ev_v = np.where(ev_p, 1.0, -1.0).astype(np.float32)
    else:
        ev_v = np.ones_like(ev_p, dtype=np.float32)

    valid = (ev_x >= 0) & (ev_x < width) & (ev_y >= 0) & (ev_y < height)
    if polarity_mode == "positive":
        valid = valid & ev_p
    
    ev_t = ev_t[valid]
    ev_x = ev_x[valid]
    ev_y = ev_y[valid]
    ev_v = ev_v[valid]

    # Pre-sort just in case, though EventStore is usually sorted by timestamp
    if len(ev_t) > 1 and not np.all(np.diff(ev_t) >= 0):
        sort_idx = np.argsort(ev_t)
        ev_t = ev_t[sort_idx]
        ev_x = ev_x[sort_idx]
        ev_y = ev_y[sort_idx]
        ev_v = ev_v[sort_idx]

    for trigger_index, trigger in enumerate(rising_triggers):
        start_us = _timestamp(trigger) + window_start_offset_us
        end_us = start_us + window_us
        
        start_idx = np.searchsorted(ev_t, start_us, side='left')
        end_idx = np.searchsorted(ev_t, end_us, side='left')
        
        if start_idx < end_idx:
            idx_x = ev_x[start_idx:end_idx]
            idx_y = ev_y[start_idx:end_idx]
            idx_v = ev_v[start_idx:end_idx]
            np.add.at(frames[trigger_index], (idx_y, idx_x), idx_v)

    return frames


def _event_increment(event, polarity_mode):
    polarity = bool(_field(event, "polarity"))
    if polarity_mode == "positive":
        return 1.0 if polarity else 0.0
    if polarity_mode == "signed":
        return 1.0 if polarity else -1.0
    return 1.0


def _trigger_edge(trigger):
    edge = _field(trigger, "edge", default=None)
    if edge is not None:
        return str(edge).lower()
    trigger_type = _field(trigger, "type", default=None)
    if trigger_type is None:
        return "rising"
    trigger_type_text = str(trigger_type).lower()
    if "rising" in trigger_type_text:
        return "rising"
    if "falling" in trigger_type_text:
        return "falling"
    return trigger_type_text


def _timestamp(record):
    return int(_field(record, "timestamp"))


def _field(record, name, default=_MISSING):
    if hasattr(record, name):
        value = getattr(record, name)
        return value() if callable(value) else value
    if isinstance(record, dict):
        if name in record:
            return record[name]
        if default is not _MISSING:
            return default
    if default is not _MISSING:
        return default
    raise AttributeError(f"{record!r} has no {name!r} field")
