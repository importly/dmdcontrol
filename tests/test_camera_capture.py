from threading import Event

import numpy as np
import pytest

from dmdcontrol.camera.capture import (
    CameraReadyState,
    CaptureResult,
    append_batch_records,
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
    trigger_configuration = {"configured": True}

    state = validate_camera_ready(FakeCapture(), trigger_configuration=trigger_configuration)

    assert isinstance(state, CameraReadyState)
    assert state.event_stream_available is True
    assert state.trigger_stream_available is True
    assert state.event_resolution == (320, 240)
    assert state.trigger_configuration == trigger_configuration


def test_validate_camera_ready_rejects_trigger_setup_errors():
    trigger_configuration = {"errors": ["setDetectorRunning(True): RuntimeError('failed')"]}

    with pytest.raises(RuntimeError, match="trigger detector setup failed"):
        validate_camera_ready(FakeCapture(), trigger_configuration=trigger_configuration)


def test_flush_stale_batches_reads_events_and_triggers():
    capture = FakeCapture()

    result = flush_stale_batches(capture, reads=2)

    assert capture.event_reads == 1
    assert capture.trigger_reads == 1
    assert result == {
        "requested_reads": 2,
        "event_reads": 1,
        "trigger_reads": 1,
        "event_batches_discarded": 0,
        "trigger_batches_discarded": 0,
        "event_count_discarded": 0,
        "trigger_count_discarded": 0,
        "stopped_early": True,
    }


def test_flush_stale_batches_reports_discarded_trigger_batches():

    class StaleCapture:

        def __init__(self):
            self.events = [[{"timestamp": 1}], None]
            self.triggers = [[{"timestamp": 2}, {"timestamp": 3}], None]

        def getNextEventBatch(self):
            return self.events.pop(0)

        def getNextTriggerBatch(self):
            return self.triggers.pop(0)

    result = flush_stale_batches(StaleCapture(), reads=4)

    assert result == {
        "requested_reads": 4,
        "event_reads": 2,
        "trigger_reads": 2,
        "event_batches_discarded": 1,
        "trigger_batches_discarded": 1,
        "event_count_discarded": 1,
        "trigger_count_discarded": 2,
        "stopped_early": True,
    }


def test_flush_stale_batches_can_preserve_trigger_batches():

    class StaleCapture:

        def __init__(self):
            self.event_reads = 0
            self.trigger_reads = 0
            self.events = [[{"timestamp": 1}], None]
            self.triggers = [[{"timestamp": 2}, {"timestamp": 3}]]

        def getNextEventBatch(self):
            self.event_reads += 1
            return self.events.pop(0)

        def getNextTriggerBatch(self):
            self.trigger_reads += 1
            return self.triggers.pop(0)

    capture = StaleCapture()

    result = flush_stale_batches(capture, reads=4, include_triggers=False)

    assert result == {
        "requested_reads": 4,
        "event_reads": 2,
        "trigger_reads": 0,
        "event_batches_discarded": 1,
        "trigger_batches_discarded": 0,
        "event_count_discarded": 1,
        "trigger_count_discarded": 0,
        "stopped_early": True,
    }
    assert capture.trigger_reads == 0
    assert capture.triggers == [[{"timestamp": 2}, {"timestamp": 3}]]


class FakeNumpyBatch:

    def __init__(self, array):
        self.array = array

    def numpy(self):
        return self.array


def test_append_batch_records_snapshots_numpy_batches():
    source = np.array(
        [(100,
          2,
          1,
          True)],
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
    destination = []

    append_batch_records(destination, FakeNumpyBatch(source), as_numpy=True)
    source["timestamp"][0] = 999
    source["x"][0] = 9

    assert destination[0]["timestamp"][0] == 100
    assert destination[0]["x"][0] == 2
    assert not np.shares_memory(destination[0], source)


class FakeWriter:

    def __init__(self):
        self.events = []
        self.triggers = []

    def writeEvents(self, events, streamName="events"):
        self.events.append((streamName, events))

    def writeTriggerPacket(self, triggers, streamName="triggers"):
        self.triggers.append((streamName, triggers))


def test_flush_stale_batches_archives_discarded_batches():

    class StaleCapture:

        def __init__(self):
            self.events = [[{"timestamp": 1}], None]
            self.triggers = [[{"timestamp": 2}], None]

        def getNextEventBatch(self):
            return self.events.pop(0)

        def getNextTriggerBatch(self):
            return self.triggers.pop(0)

    archive_writer = FakeWriter()

    result = flush_stale_batches(
        StaleCapture(),
        reads=4,
        archive_writer=archive_writer,
    )

    assert archive_writer.events == [
        ("events",
         [{
             "timestamp": 1}]),
    ]
    assert archive_writer.triggers == [
        ("triggers",
         [{
             "timestamp": 2}]),
    ]
    assert result["event_count_discarded"] == 1
    assert result["trigger_count_discarded"] == 1


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


def test_flush_stale_batches_drains_until_idle():
    capture = FakeLiveCapture()
    capture.event_batches = [["stale-events"], None, ["not-read"]]
    capture.trigger_batches = [["stale-triggers"], None, ["not-read"]]

    from dmdcontrol.camera.capture import flush_stale_batches

    flush_stale_batches(capture, reads=10)

    assert capture.event_reads == 2
    assert capture.trigger_reads == 2
    assert capture.event_batches == [["not-read"]]
    assert capture.trigger_batches == [["not-read"]]


def test_record_until_trigger_count_reads_post_trigger_event_batches():
    capture = FakeLiveCapture()
    capture.event_batches = [None, ["tail1"], ["tail2"]]
    capture.trigger_batches = [[object(), object()], None, None]
    writer = FakeWriter()

    result = record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count=2,
        timeout_s=1.0,
        idle_sleep_s=0.0,
        post_trigger_event_batches=2,
    )

    assert result.trigger_count == 2
    assert result.event_batch_count == 2
    assert len(writer.events) == 2
    assert writer.events[0][1] == ["tail1"]
    assert writer.events[1][1] == ["tail2"]


def test_record_until_trigger_count_waits_until_events_reach_trigger_window():
    capture = FakeLiveCapture()
    capture.event_batches = [
        [{
            "timestamp": 100,
            "x": 1,
            "y": 1,
            "polarity": True}],
        [{
            "timestamp": 160,
            "x": 2,
            "y": 1,
            "polarity": True}],
        [{
            "timestamp": 260,
            "x": 3,
            "y": 1,
            "polarity": True}],
    ]
    capture.trigger_batches = [
        [{
            "timestamp": 200,
            "edge": "rising"}],
    ]
    writer = FakeWriter()

    result = record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count=1,
        timeout_s=1.0,
        idle_sleep_s=0.0,
        post_trigger_event_time_us=50,
    )

    assert result.trigger_count == 1
    assert result.event_count == 3
    assert result.event_batch_count == 3
    assert result.event_time_range_us == (100, 260)


def test_record_until_trigger_count_reports_capture_time_ranges():
    capture = FakeLiveCapture()
    capture.event_batches = [
        [
            {
                "timestamp": 100,
                "x": 1,
                "y": 1,
                "polarity": True},
            {
                "timestamp": 120,
                "x": 2,
                "y": 1,
                "polarity": True},
        ],
        [
            {
                "timestamp": 250,
                "x": 3,
                "y": 1,
                "polarity": False},
        ],
    ]
    capture.trigger_batches = [
        [{
            "timestamp": 110,
            "edge": "rising"}],
        [{
            "timestamp": 260,
            "edge": "rising"}],
    ]
    writer = FakeWriter()

    result = record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count=2,
        timeout_s=1.0,
        idle_sleep_s=0.0,
    )

    assert result.event_count == 3
    assert result.event_time_range_us == (100, 250)
    assert result.trigger_time_range_us == (110, 260)


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


def test_record_until_trigger_count_drains_tail_batches_after_stop_event():
    stop_event = Event()

    class DelayedTailCapture(FakeCapture):

        def isRunning(self):
            return True

        def getNextEventBatch(self):
            self.event_reads += 1
            if stop_event.is_set() and self.event_reads == 2:
                return [{"timestamp": 300, "x": 1, "y": 1, "polarity": True}]
            return None

        def getNextTriggerBatch(self):
            self.trigger_reads += 1
            if stop_event.is_set() and self.trigger_reads == 2:
                return [{"timestamp": 250, "edge": "rising"}]
            return None

    capture = DelayedTailCapture()
    writer = FakeWriter()
    stop_event.set()

    result = record_until_trigger_count(
        capture,
        writer,
        expected_trigger_count=None,
        timeout_s=10.0,
        idle_sleep_s=0.0,
        stop_event=stop_event,
    )

    assert result.stopped is True
    assert result.event_count == 1
    assert result.trigger_count == 1
    assert writer.events[0][1][0]["timestamp"] == 300
    assert writer.triggers[0][1][0]["timestamp"] == 250
