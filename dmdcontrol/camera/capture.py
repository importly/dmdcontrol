from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Event, Thread


@dataclass(frozen=True)
class CameraReadyState:
    event_stream_available: bool
    trigger_stream_available: bool
    event_resolution: tuple[int, int]


@dataclass(frozen=True)
class CaptureResult:
    trigger_count: int
    event_batch_count: int
    trigger_batch_count: int
    timed_out: bool
    stopped: bool = False


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
    ):
        self.capture = capture
        self.writer = writer
        self.expected_trigger_count = expected_trigger_count
        self.timeout_s = timeout_s
        self.idle_sleep_s = idle_sleep_s
        self.on_events = on_events
        self.on_triggers = on_triggers
        self.record_fn = record_fn or record_until_trigger_count
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
            )
        except BaseException as exc:
            self.error = exc


def validate_camera_ready(capture) -> CameraReadyState:
    event_available = bool(capture.isEventStreamAvailable())
    trigger_available = bool(capture.isTriggerStreamAvailable())
    if not event_available:
        raise RuntimeError("Camera event stream is not available.")
    if not trigger_available:
        raise RuntimeError("Camera trigger stream is not available.")
    return CameraReadyState(
        event_stream_available=event_available,
        trigger_stream_available=trigger_available,
        event_resolution=tuple(capture.getEventResolution()),
    )


def flush_stale_batches(capture, reads=3) -> None:
    for _ in range(reads):
        if hasattr(capture, "getNextEventBatch"):
            capture.getNextEventBatch()
        if hasattr(capture, "getNextTriggerBatch"):
            capture.getNextTriggerBatch()


def append_batch_records(destination, batch, as_numpy=False) -> None:
    if batch is None:
        return
    if as_numpy and hasattr(batch, "numpy"):
        destination.append(batch.numpy())
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


def record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count,
        timeout_s,
        idle_sleep_s=0.001,
        on_events=None,
        on_triggers=None,
        stop_event=None,
) -> CaptureResult:
    deadline = (
        time.time() + timeout_s
        if timeout_s is not None and timeout_s > 0
        else None
    )
    trigger_count = 0
    event_batch_count = 0
    trigger_batch_count = 0
    timed_out = False
    stopped = False

    while True:
        if stop_event is not None and stop_event.is_set():
            stopped = True
            break
        if hasattr(capture, "isRunning") and not capture.isRunning():
            break
        if deadline is not None and time.time() >= deadline:
            timed_out = True
            break

        did_work = False
        events = (
            capture.getNextEventBatch()
            if hasattr(capture, "getNextEventBatch")
            else None
        )
        if events is not None:
            writer.writeEvents(events, streamName="events")
            if on_events is not None:
                on_events(events)
            event_batch_count += 1
            did_work = True

        triggers = (
            capture.getNextTriggerBatch()
            if hasattr(capture, "getNextTriggerBatch")
            else None
        )
        if triggers is not None:
            writer.writeTriggerPacket(triggers, streamName="triggers")
            if on_triggers is not None:
                on_triggers(triggers)
            trigger_batch_count += 1
            trigger_count += _batch_len(triggers)
            did_work = True

        if expected_trigger_count is not None and trigger_count >= expected_trigger_count:
            break
        if not did_work and idle_sleep_s > 0:
            time.sleep(idle_sleep_s)

    return CaptureResult(
        trigger_count=trigger_count,
        event_batch_count=event_batch_count,
        trigger_batch_count=trigger_batch_count,
        timed_out=timed_out,
        stopped=stopped,
    )
