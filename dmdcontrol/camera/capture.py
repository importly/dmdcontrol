from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event, Thread
from typing import Any

import numpy as np

DEFAULT_STOP_DRAIN_READS = 8
DEFAULT_STOP_DRAIN_IDLE_READS = 2


@dataclass(frozen=True)
class CameraReadyState:
    event_stream_available: bool
    trigger_stream_available: bool
    event_resolution: tuple[int, int]
    trigger_configuration: dict | None = None
    initial_flush: dict | None = None
    stream_rearm: dict | None = None
    usb_reset: dict | None = None
    power_cycle: dict | None = None


@dataclass(frozen=True)
class CaptureResult:
    trigger_count: int
    event_batch_count: int
    trigger_batch_count: int
    timed_out: bool
    stopped: bool = False
    event_count: int = 0
    event_time_range_us: tuple[int, int] | None = None
    trigger_time_range_us: tuple[int, int] | None = None


class AsyncCapture:

    def __init__(
        self,
        capture,
        writer,
        expected_trigger_count,
        timeout_s,
        idle_sleep_s=0.001,
        on_events=None,
        on_triggers=None,
        record_fn=None,
        post_trigger_event_batches=0,
        post_trigger_event_time_us=0,
        stop_drain_reads=DEFAULT_STOP_DRAIN_READS,
        stop_drain_idle_reads=DEFAULT_STOP_DRAIN_IDLE_READS,
    ):
        self.capture = capture
        self.writer = writer
        self.expected_trigger_count = expected_trigger_count
        self.timeout_s = timeout_s
        self.idle_sleep_s = idle_sleep_s
        self.on_events = on_events
        self.on_triggers = on_triggers
        self.record_fn = record_fn or record_until_trigger_count
        self.post_trigger_event_batches = int(post_trigger_event_batches or 0)
        self.post_trigger_event_time_us = int(post_trigger_event_time_us or 0)
        self.stop_drain_reads = int(stop_drain_reads or 0)
        self.stop_drain_idle_reads = int(stop_drain_idle_reads or 0)
        self.result = None
        self.error = None
        self._stop_event = Event()
        self._thread = Thread(target=self._record, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def join(self, timeout=None):
        self._thread.join(timeout=timeout)
        if self.error is not None:
            raise self.error
        return self.result

    def _record(self):
        try:
            self.result = self.record_fn(
                self.capture,
                self.writer,
                expected_trigger_count=self.expected_trigger_count,
                timeout_s=self.timeout_s,
                idle_sleep_s=self.idle_sleep_s,
                on_events=self.on_events,
                on_triggers=self.on_triggers,
                stop_event=self._stop_event,
                post_trigger_event_batches=self.post_trigger_event_batches,
                post_trigger_event_time_us=self.post_trigger_event_time_us,
                stop_drain_reads=self.stop_drain_reads,
                stop_drain_idle_reads=self.stop_drain_idle_reads,
            )
        except BaseException as exc:
            self.error = exc


def validate_camera_ready(
    capture,
    stream_rearm=None,
    usb_reset=None,
    power_cycle=None,
    trigger_configuration=None,
) -> CameraReadyState:
    event_available = bool(capture.isEventStreamAvailable())
    trigger_available = bool(capture.isTriggerStreamAvailable())
    if not event_available:
        raise RuntimeError("Camera event stream is not available.")
    if not trigger_available:
        raise RuntimeError("Camera trigger stream is not available.")
    trigger_errors = (
        trigger_configuration.get("errors") if isinstance(trigger_configuration,
                                                          dict) else None)
    if trigger_errors:
        raise RuntimeError(
            "Camera trigger detector setup failed: " +
            "; ".join(str(error) for error in trigger_errors))
    return CameraReadyState(
        event_stream_available=event_available,
        trigger_stream_available=trigger_available,
        event_resolution=tuple(capture.getEventResolution()),
        trigger_configuration=trigger_configuration,
        stream_rearm=stream_rearm,
        usb_reset=usb_reset,
        power_cycle=power_cycle,
    )


def flush_stale_batches(capture, reads=3, include_triggers=True) -> dict:
    requested_reads = max(0, int(reads))
    stats = {
        "requested_reads": requested_reads,
        "event_reads": 0,
        "trigger_reads": 0,
        "event_batches_discarded": 0,
        "trigger_batches_discarded": 0,
        "event_count_discarded": 0,
        "trigger_count_discarded": 0,
        "stopped_early": False,
    }
    for _ in range(requested_reads):
        did_work = False
        if hasattr(capture, "getNextEventBatch"):
            stats["event_reads"] += 1
            events = capture.getNextEventBatch()
            if events is not None:
                stats["event_batches_discarded"] += 1
                stats["event_count_discarded"] += _batch_len(events)
                did_work = True
        if include_triggers and hasattr(capture, "getNextTriggerBatch"):
            stats["trigger_reads"] += 1
            triggers = capture.getNextTriggerBatch()
            if triggers is not None:
                stats["trigger_batches_discarded"] += 1
                stats["trigger_count_discarded"] += _batch_len(triggers)
                did_work = True
        if not did_work:
            stats["stopped_early"] = True
            break
    return stats


def append_batch_records(destination, batch, as_numpy=False) -> None:
    if batch is None:
        return
    if as_numpy and hasattr(batch, "numpy"):
        records = batch.numpy()
        destination.append(records.copy() if hasattr(records, "copy") else records)
    else:
        try:
            destination.extend(list(batch))
        except TypeError:
            destination.append(batch)


def _batch_len(batch) -> int:
    try:
        return len(batch)
    except TypeError:
        return 0


def _merge_time_range(current, update):
    if update is None:
        return current
    if current is None:
        return update
    return min(current[0], update[0]), max(current[1], update[1])


def _batch_time_range_us(batch):
    if batch is None or _batch_len(batch) == 0:
        return None
    if hasattr(batch, "getLowestTime") and hasattr(batch, "getHighestTime"):
        return int(batch.getLowestTime()), int(batch.getHighestTime())
    if isinstance(batch, np.ndarray):
        field_names = batch.dtype.names or ()
        timestamp_field = "timestamp" if "timestamp" in field_names else "t"
        if timestamp_field not in field_names:
            return None
        timestamps = batch[timestamp_field]
        if len(timestamps) == 0:
            return None
        return int(np.min(timestamps)), int(np.max(timestamps))
    try:
        records = list(batch)
    except TypeError:
        records = [batch]
    timestamps = []
    for record in records:
        timestamp = _record_timestamp_or_none(record)
        if timestamp is not None:
            timestamps.append(timestamp)
    if not timestamps:
        return None
    return min(timestamps), max(timestamps)


def _record_timestamp_or_none(record):
    for name in ("timestamp", "t"):
        if hasattr(record, name):
            value: Any = getattr(record, name)
            return int(value() if callable(value) else value)
        if isinstance(record, dict) and name in record:
            return int(record[name])
        if (isinstance(record, np.void) and record.dtype.names and name in record.dtype.names):
            return int(record[name])
    return None


def _post_trigger_event_window_reached(
        event_time_range_us,
        trigger_time_range_us,
        post_trigger_event_time_us):
    if post_trigger_event_time_us <= 0 or trigger_time_range_us is None:
        return True
    if event_time_range_us is None:
        return False
    return (event_time_range_us[1] >= trigger_time_range_us[1] + post_trigger_event_time_us)


def record_until_trigger_count(
    capture,
    writer,
    expected_trigger_count,
    timeout_s,
    idle_sleep_s=0.001,
    on_events=None,
    on_triggers=None,
    stop_event=None,
    post_trigger_event_batches=0,
    post_trigger_event_time_us=0,
    stop_drain_reads=DEFAULT_STOP_DRAIN_READS,
    stop_drain_idle_reads=DEFAULT_STOP_DRAIN_IDLE_READS,
) -> CaptureResult:
    deadline = (time.time() + timeout_s if timeout_s is not None and timeout_s > 0 else None)
    trigger_count = 0
    event_count = 0
    event_batch_count = 0
    trigger_batch_count = 0
    event_time_range_us = None
    trigger_time_range_us = None
    timed_out = False
    stopped = False

    def read_event_batch():
        nonlocal event_count, event_batch_count, event_time_range_us
        events = (capture.getNextEventBatch() if hasattr(capture, "getNextEventBatch") else None)
        if events is None:
            return False
        writer.writeEvents(events, streamName="events")
        if on_events is not None:
            on_events(events)
        event_count += _batch_len(events)
        event_time_range_us = _merge_time_range(
            event_time_range_us,
            _batch_time_range_us(events),
        )
        event_batch_count += 1
        return True

    def read_trigger_batch():
        nonlocal trigger_count, trigger_batch_count, trigger_time_range_us
        triggers = (
            capture.getNextTriggerBatch() if hasattr(capture,
                                                     "getNextTriggerBatch") else None)
        if triggers is None:
            return False
        writer.writeTriggerPacket(triggers, streamName="triggers")
        if on_triggers is not None:
            on_triggers(triggers)
        trigger_batch_count += 1
        trigger_count += _batch_len(triggers)
        trigger_time_range_us = _merge_time_range(
            trigger_time_range_us,
            _batch_time_range_us(triggers),
        )
        return True

    def read_available_batches():
        event_work = read_event_batch()
        trigger_work = read_trigger_batch()
        return event_work or trigger_work

    def drain_after_stop():
        drain_reads = max(0, int(stop_drain_reads or 0))
        idle_limit = max(1, int(stop_drain_idle_reads or 0))
        idle_reads = 0
        for _ in range(drain_reads):
            if hasattr(capture, "isRunning") and not capture.isRunning():
                break
            did_work = read_available_batches()
            if did_work:
                idle_reads = 0
                continue
            idle_reads += 1
            if idle_reads >= idle_limit:
                break
            if idle_sleep_s > 0:
                time.sleep(idle_sleep_s)

    while True:
        if stop_event is not None and stop_event.is_set():
            stopped = True
            break
        if hasattr(capture, "isRunning") and not capture.isRunning():
            break
        if deadline is not None and time.time() >= deadline:
            timed_out = True
            break

        did_work = read_available_batches()

        if (expected_trigger_count is not None and trigger_count >= expected_trigger_count):
            post_batches_remaining = max(0, int(post_trigger_event_batches or 0))
            post_trigger_event_time_us = max(0, int(post_trigger_event_time_us or 0))
            while post_batches_remaining > 0 or not _post_trigger_event_window_reached(
                    event_time_range_us,
                    trigger_time_range_us,
                    post_trigger_event_time_us,
            ):
                if stop_event is not None and stop_event.is_set():
                    stopped = True
                    break
                if hasattr(capture, "isRunning") and not capture.isRunning():
                    break
                if deadline is not None and time.time() >= deadline:
                    timed_out = True
                    break

                if not read_event_batch():
                    if idle_sleep_s > 0:
                        time.sleep(idle_sleep_s)
                    continue

                if post_batches_remaining > 0:
                    post_batches_remaining -= 1
            break
        if not did_work and idle_sleep_s > 0:
            time.sleep(idle_sleep_s)

    if stopped:
        drain_after_stop()

    return CaptureResult(
        trigger_count=trigger_count,
        event_batch_count=event_batch_count,
        trigger_batch_count=trigger_batch_count,
        timed_out=timed_out,
        stopped=stopped,
        event_count=event_count,
        event_time_range_us=event_time_range_us,
        trigger_time_range_us=trigger_time_range_us,
    )
