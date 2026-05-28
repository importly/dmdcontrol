from threading import Event

from dmdcontrol.camera.capture import (
    CameraReadyState,
    CaptureResult,
    flush_stale_batches,
    record_until_trigger_count,
    validate_camera_ready,
)


class FakeCapture:
    def __init__(self):
        self.event_reads = 0
        self.trigger_reads = 0

    def isEventStreamAvailable(self):
        return True

    def isTriggerStreamAvailable(self):
        return True

    def getEventResolution(self):
        return (320, 240)

    def getNextEventBatch(self):
        self.event_reads += 1
        return None

    def getNextTriggerBatch(self):
        self.trigger_reads += 1
        return None


def test_validate_camera_ready_requires_event_and_trigger_streams():
    state = validate_camera_ready(FakeCapture())

    assert isinstance(state, CameraReadyState)
    assert state.event_stream_available is True
    assert state.trigger_stream_available is True
    assert state.event_resolution == (320, 240)


def test_flush_stale_batches_reads_events_and_triggers():
    capture = FakeCapture()

    flush_stale_batches(capture, reads=2)

    assert capture.event_reads == 2
    assert capture.trigger_reads == 2


class FakeWriter:
    def __init__(self):
        self.events = []
        self.triggers = []

    def writeEvents(self, events, streamName="events"):
        self.events.append((streamName, events))

    def writeTriggerPacket(self, triggers, streamName="triggers"):
        self.triggers.append((streamName, triggers))


class FakeLiveCapture(FakeCapture):
    def __init__(self):
        super().__init__()
        self.event_batches = [["e1"], None, ["e2"], None]
        self.trigger_batches = [[object(), object()], None, [object()], None]
        self.running = True

    def isRunning(self):
        return self.running

    def getNextEventBatch(self):
        self.event_reads += 1
        return self.event_batches.pop(0) if self.event_batches else None

    def getNextTriggerBatch(self):
        self.trigger_reads += 1
        return self.trigger_batches.pop(0) if self.trigger_batches else None


def test_record_until_trigger_count_writes_events_and_triggers():
    capture = FakeLiveCapture()
    writer = FakeWriter()

    result = record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count=3,
        timeout_s=1.0,
        idle_sleep_s=0.0,
    )

    assert isinstance(result, CaptureResult)
    assert result.trigger_count == 3
    assert result.event_batch_count == 2
    assert result.trigger_batch_count == 2
    assert result.timed_out is False
    assert len(writer.events) == 2
    assert len(writer.triggers) == 2


def test_record_until_trigger_count_stops_when_stop_event_is_set():
    capture = FakeLiveCapture()
    capture.event_batches = [None, None, None]
    capture.trigger_batches = [None, None, None]
    writer = FakeWriter()
    stop_event = Event()

    def stop_after_first_idle_read():
        stop_event.set()
        return None

    capture.getNextTriggerBatch = stop_after_first_idle_read

    result = record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count=None,
        timeout_s=10.0,
        idle_sleep_s=0.0,
        stop_event=stop_event,
    )

    assert result.trigger_count == 0
    assert result.timed_out is False
    assert result.stopped is True
