import json
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def _parse_camera_args(module, args):
    return module.build_parser().parse_args(["--exposure-us", "600", *args])


def test_pair_capture_parser_requires_exposure():
    from dmdcontrol.camera import pair_capture

    with pytest.raises(SystemExit):
        pair_capture.build_parser().parse_args([])


def _fake_run_directory(tmp_path):
    return SimpleNamespace(
        path=tmp_path,
        raw_recording_path=tmp_path / "raw.aedat4",
        raw_full_recording_path=tmp_path / "raw_full.aedat4",
        metadata_path=tmp_path / "metadata.json",
        command_path=tmp_path / "command.txt",
        log_path=tmp_path / "run.log",
        triggers_path=tmp_path / "triggers.csv",
        accumulated_path=tmp_path / "accumulated.npy",
        timing_path=tmp_path / "timing.json",
        contact_sheet_path=tmp_path / "contact_sheet.png",
        summary_path=tmp_path / "summary.json",
    )


def _startup_leader(trigger_count=8, entries_count=4):
    return {
        "vsyncs": 2,
        "trigger_count": trigger_count,
        "entries_count": entries_count,
        "trig2_mode": "per_bitplane",
        "frame_role": "blank_startup_leader",
    }


def test_pair_capture_live_records_while_dmd_runtime_is_active(monkeypatch, tmp_path):
    from dmdcontrol.camera import pair_capture

    events = []
    record_started = Event()
    runtime_can_finish = Event()
    fake_capture = Mock()
    fake_writer = Mock()
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        pair_capture,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        pair_capture,
        "_open_ready_camera",
        lambda run, args: events.append("camera_ready") or (fake_capture, fake_writer, ready),
    )

    def fake_record(*args, **kwargs):
        events.append("record_start")
        record_started.set()
        assert runtime_can_finish.wait(timeout=1.0)
        events.append("record_stop")
        return SimpleNamespace(
            trigger_count=0,
            event_batch_count=0,
            trigger_batch_count=0,
            timed_out=False,
        )

    monkeypatch.setattr(pair_capture, "record_until_trigger_count", fake_record)

    def fake_run(pair_request, before_start):
        assert pair_request.test == "a-kernel-b-static"
        events.append("dmd_prepare")
        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})
        events.append("dmd_active")
        assert record_started.wait(timeout=1.0)
        events.append("dmd_observed_recording")
        runtime_can_finish.set()
        events.append("dmd_return")

    monkeypatch.setattr(pair_capture, "run_pair_runtime", fake_run)

    args = _parse_camera_args(
        pair_capture,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
        ])

    assert pair_capture.live(args) == 0
    assert events.index("record_start") < events.index("dmd_return")
    assert events.index("dmd_active") < events.index("record_stop")


def test_pair_capture_live_records_until_dmd_runtime_finishes(monkeypatch, tmp_path):
    from dmdcontrol.camera import pair_capture

    record_started = Event()
    runtime_can_finish = Event()
    record_kwargs = {}
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        pair_capture,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        pair_capture,
        "_open_ready_camera",
        lambda run, args: (Mock(), Mock(), ready),
    )

    def fake_record(*args, **kwargs):
        record_kwargs.update(kwargs)
        record_started.set()
        assert runtime_can_finish.wait(timeout=1.0)
        return SimpleNamespace(
            trigger_count=520,
            event_batch_count=0,
            trigger_batch_count=0,
            timed_out=False,
        )

    monkeypatch.setattr(pair_capture, "record_until_trigger_count", fake_record)

    def fake_run(pair_args, before_start):
        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})
        assert record_started.wait(timeout=1.0)
        runtime_can_finish.set()

    monkeypatch.setattr(pair_capture, "run_pair_runtime", fake_run)

    args = _parse_camera_args(
        pair_capture,
        [
            "--output-root",
            str(tmp_path),
            "--test",
            "a-kernel-b-static",
            "--runtime-seconds",
            "1",
        ])

    assert pair_capture.live(args) == 0
    assert record_kwargs["expected_trigger_count"] is None


def test_pair_capture_live_writes_capture_artifacts_with_event_filter(monkeypatch, tmp_path):
    from dmdcontrol.camera import pair_capture

    record_started = Event()
    runtime_can_finish = Event()
    artifact_call = {}
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        pair_capture,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        pair_capture,
        "_open_ready_camera",
        lambda run, args: (Mock(), Mock(), ready),
    )

    def fake_record(*args, **kwargs):
        kwargs["on_events"]([{"timestamp": 105, "x": 2, "y": 1, "polarity": True}])
        kwargs["on_triggers"]([{"timestamp": 100, "edge": "rising"}])
        record_started.set()
        assert runtime_can_finish.wait(timeout=1.0)
        return SimpleNamespace(
            trigger_count=1,
            event_batch_count=1,
            trigger_batch_count=1,
            timed_out=False,
        )

    monkeypatch.setattr(pair_capture, "record_until_trigger_count", fake_record)

    startup_leader = _startup_leader()
    display_sequence = {
        "startup_policy": "blank_leader",
        "lut_slots_per_source_frame": 4,
    }

    def fake_run(pair_args, before_start):
        before_start(
            {
                "state_a": {
                    "timing": {}},
                "state_b": {
                    "timing": {}},
                "startup_leader": startup_leader,
                "display_sequence": display_sequence,
            })
        assert record_started.wait(timeout=1.0)
        runtime_can_finish.set()

    monkeypatch.setattr(pair_capture, "run_pair_runtime", fake_run)

    def fake_write_capture_artifacts(run, **kwargs):
        artifact_call.update(kwargs)
        return {
            "actual_trigger_count": len(kwargs["triggers"]),
            "frame_artifacts": ["accumulated_001.png"],
        }

    monkeypatch.setattr(pair_capture, "write_capture_artifacts", fake_write_capture_artifacts)

    args = _parse_camera_args(
        pair_capture,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
            "--test",
            "checkerboard",
            "--exposure-us",
            "600",
            "--event-noise-filter",
            "local-support",
            "--event-filter-delta-us",
            "50000",
            "--event-filter-window-px",
            "3",
            "--event-filter-threshold",
            "2",
            "--event-filter-polarity",
            "same",
        ])

    assert pair_capture.live(args) == 0
    assert artifact_call["events"] == [{"timestamp": 105, "x": 2, "y": 1, "polarity": True}]
    assert artifact_call["triggers"] == [{"timestamp": 100, "edge": "rising"}]
    assert artifact_call["resolution"] == (320, 240)
    assert artifact_call["window_us"] == 600
    assert artifact_call["startup_leader_trigger_count"] == 8
    assert artifact_call["event_noise_filter"].enabled is True
    assert artifact_call["event_noise_filter"].delta_t_us == 50000
    assert artifact_call["event_noise_filter"].window_px == 3
    assert artifact_call["event_noise_filter"].threshold == 2
    assert artifact_call["event_noise_filter"].polarity == "same"
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "pair-capture"
    assert metadata["dmd"] == {
        "test": "checkerboard",
        "test_b": "dot",
        "b_dot_x": 960,
        "b_dot_y": 540,
        "b_dot_radius": 40,
        "kernel_px": 129,
        "exposure_us": 600,
        "runtime_seconds": 1,
        "paired_startup_leader_vsyncs": 16,
        "dmd_config": None,
    }
    assert metadata["requested_command_shape"] == [
        "--test",
        "checkerboard",
        "--test-b",
        "dot",
        "--b-dot-x",
        "960",
        "--b-dot-y",
        "540",
        "--b-dot-radius",
        "40",
        "--kernel-px",
        "129",
        "--exposure-us",
        "600",
        "--runtime-seconds",
        "1",
        "--paired-startup-leader-vsyncs",
        "16",
    ]
    assert metadata["expected_shape"] == {
        "kernel_count": None,
        "input_image_count": None,
    }
    assert metadata["trigger_policy"] == {
        "channel": "TRIG_OUT_2",
        "source_dmd": "A",
        "edge": "rising",
        "rising_delay_us": 0,
        "falling_delay_us": 20,
    }
    assert metadata["event_noise_filter"]["enabled"] is True
    assert metadata["event_noise_filter"]["delta_t_us"] == 50000
    assert metadata["startup_leader"] == startup_leader
    assert metadata["display_sequence"] == display_sequence


def test_pair_capture_live_limits_in_memory_artifact_batches(monkeypatch, tmp_path):
    from dmdcontrol.camera import pair_capture

    record_started = Event()
    runtime_can_finish = Event()
    artifact_call = {}
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        pair_capture,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        pair_capture,
        "_open_ready_camera",
        lambda run, args: (Mock(), Mock(), ready),
    )

    def fake_record(*args, **kwargs):
        kwargs["on_events"](
            [
                {
                    "timestamp": 101,
                    "x": 1,
                    "y": 1,
                    "polarity": True},
                {
                    "timestamp": 112,
                    "x": 9,
                    "y": 9,
                    "polarity": True},
            ])
        kwargs["on_triggers"](
            [
                {
                    "timestamp": 100,
                    "edge": "rising"},
                {
                    "timestamp": 200,
                    "edge": "rising"},
            ])
        kwargs["on_events"](
            [
                {
                    "timestamp": 104,
                    "x": 2,
                    "y": 2,
                    "polarity": True},
                {
                    "timestamp": 120,
                    "x": 3,
                    "y": 3,
                    "polarity": True},
            ])
        kwargs["on_triggers"]([
            {
                "timestamp": 300,
                "edge": "rising"},
        ])
        record_started.set()
        assert runtime_can_finish.wait(timeout=1.0)
        return SimpleNamespace(
            trigger_count=3,
            event_batch_count=2,
            trigger_batch_count=2,
            timed_out=False,
        )

    monkeypatch.setattr(pair_capture, "record_until_trigger_count", fake_record)

    startup_leader = _startup_leader(trigger_count=2, entries_count=1)

    def fake_run(pair_args, before_start):
        before_start(
            {
                "state_a": {
                    "timing": {}},
                "state_b": {
                    "timing": {}},
                "startup_leader": startup_leader,
            })
        assert record_started.wait(timeout=1.0)
        runtime_can_finish.set()

    monkeypatch.setattr(pair_capture, "run_pair_runtime", fake_run)

    def fake_write_capture_artifacts(run, **kwargs):
        artifact_call.update(kwargs)
        return {
            "actual_trigger_count": len(kwargs["triggers"]),
            "frame_artifacts": ["accumulated_001.png"],
        }

    monkeypatch.setattr(pair_capture, "write_capture_artifacts", fake_write_capture_artifacts)

    args = _parse_camera_args(
        pair_capture,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
            "--exposure-us",
            "10",
            "--max-accumulation-triggers",
            "1",
        ])

    assert pair_capture.live(args) == 0
    assert artifact_call["max_accumulation_triggers"] == 1
    assert artifact_call["startup_leader_trigger_count"] == 2
    assert artifact_call["triggers"] == [
        {
            "timestamp": 100,
            "edge": "rising"},
        {
            "timestamp": 200,
            "edge": "rising"},
        {
            "timestamp": 300,
            "edge": "rising"},
    ]
    assert artifact_call["events"] == [
        {
            "timestamp": 101,
            "x": 1,
            "y": 1,
            "polarity": True},
        {
            "timestamp": 112,
            "x": 9,
            "y": 9,
            "polarity": True},
        {
            "timestamp": 104,
            "x": 2,
            "y": 2,
            "polarity": True},
        {
            "timestamp": 120,
            "x": 3,
            "y": 3,
            "polarity": True},
    ]


def test_sync_check_live_records_while_dmd_runtime_is_active(monkeypatch, tmp_path):
    from dmdcontrol.camera import sync_check

    events = []
    record_started = Event()
    runtime_can_finish = Event()
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        sync_check,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        sync_check,
        "_open_ready_camera",
        lambda run, args: events.append("camera_ready") or (Mock(), Mock(), ready, None),
    )

    def fake_run(pair_args, before_start):
        events.append("dmd_prepare")
        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})
        events.append("dmd_active")
        assert record_started.wait(timeout=1.0)
        events.append("dmd_observed_recording")
        runtime_can_finish.set()
        events.append("dmd_return")

    monkeypatch.setattr(sync_check, "run_pair_runtime", fake_run)

    def fake_record(*args, **kwargs):
        events.append("record_start")
        record_started.set()
        assert runtime_can_finish.wait(timeout=1.0)
        events.append("record_stop")
        return SimpleNamespace(
            trigger_count=5,
            event_batch_count=0,
            trigger_batch_count=0,
            timed_out=False,
        )

    monkeypatch.setattr(sync_check, "record_until_trigger_count", fake_record)

    args = _parse_camera_args(
        sync_check,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
        ])

    assert sync_check.live(args) == 0
    assert events.index("record_start") < events.index("dmd_return")
    assert events.index("dmd_active") < events.index("record_stop")


def test_sync_check_raw_full_spans_setup_and_active_capture(monkeypatch, tmp_path):
    from queue import Empty, Queue

    from dmdcontrol.camera import sync_check

    class QueuedCapture:

        def __init__(self):
            self.events = Queue()
            self.triggers = Queue()

        def isRunning(self):
            return True

        def getNextEventBatch(self):
            try:
                return self.events.get_nowait()
            except Empty:
                return None

        def getNextTriggerBatch(self):
            try:
                return self.triggers.get_nowait()
            except Empty:
                return None

    class RecordingWriter:

        def __init__(self):
            self.events = []
            self.triggers = []
            self.event_written = Event()
            self.trigger_written = Event()

        def writeEvents(self, events, streamName="events"):
            self.events.append((streamName, events))
            self.event_written.set()

        def writeTriggerPacket(self, triggers, streamName="triggers"):
            self.triggers.append((streamName, triggers))
            self.trigger_written.set()

    capture = QueuedCapture()
    writer = RecordingWriter()
    full_writer = RecordingWriter()
    ready = SimpleNamespace(event_resolution=(320, 240))

    def fake_run(pair_args, before_start):
        capture.events.put([{"timestamp": 10, "phase": "setup"}])
        capture.triggers.put([{"timestamp": 11, "phase": "setup"}])
        assert full_writer.event_written.wait(timeout=1.0)
        assert full_writer.trigger_written.wait(timeout=1.0)

        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})

        capture.events.put([{"timestamp": 20, "phase": "active"}])
        capture.triggers.put([{"timestamp": 21, "phase": "active"}])
        assert writer.event_written.wait(timeout=1.0)
        assert writer.trigger_written.wait(timeout=1.0)

    monkeypatch.setattr(sync_check, "run_pair_runtime", fake_run)
    monkeypatch.setattr(sync_check, "write_capture_artifacts", lambda *a, **k: {})

    args = _parse_camera_args(
        sync_check,
        [
            "--runtime-seconds",
            "1",
            "--camera-flush-reads",
            "2",
        ],
    )
    run = _fake_run_directory(tmp_path)

    assert sync_check.live_capture(
        args,
        run,
        capture,
        writer,
        ready,
        full_writer=full_writer,
    ) == 0

    assert [batch[1][0]["phase"] for batch in full_writer.events] == [
        "setup",
        "active",
    ]
    assert [batch[1][0]["phase"] for batch in writer.events] == ["active"]
    assert [batch[1][0]["phase"] for batch in full_writer.triggers] == [
        "setup",
        "active",
    ]
    assert [batch[1][0]["phase"] for batch in writer.triggers] == ["active"]
    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert metadata["artifacts"][:2] == ["raw.aedat4", "raw_full.aedat4"]
    assert metadata["raw_full_capture"]["path"] == str(run.raw_full_recording_path)


def test_live_stops_recording_when_dmd_runtime_raises(monkeypatch, tmp_path):
    from dmdcontrol.camera import pair_capture

    events = []
    record_started = Event()
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        pair_capture,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        pair_capture,
        "_open_ready_camera",
        lambda run, args: (Mock(), Mock(), ready),
    )

    def fake_record(*args, **kwargs):
        events.append("record_start")
        record_started.set()
        stop_event = kwargs.get("stop_event")
        if stop_event is None:
            events.append("missing_stop_event")
            return SimpleNamespace(
                trigger_count=0,
                event_batch_count=0,
                trigger_batch_count=0,
                timed_out=False,
            )
        assert stop_event.wait(timeout=1.0)
        events.append("record_stop")
        return SimpleNamespace(
            trigger_count=0,
            event_batch_count=0,
            trigger_batch_count=0,
            timed_out=False,
        )

    monkeypatch.setattr(pair_capture, "record_until_trigger_count", fake_record)

    def fake_run(pair_args, before_start):
        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})
        assert record_started.wait(timeout=1.0)
        raise RuntimeError("DMD runtime failed")

    monkeypatch.setattr(pair_capture, "run_pair_runtime", fake_run)

    args = _parse_camera_args(
        pair_capture,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
        ])

    try:
        pair_capture.live(args)
    except RuntimeError as exc:
        assert str(exc) == "DMD runtime failed"
    else:
        raise AssertionError("live() should re-raise the DMD runtime failure")

    assert "record_stop" in events


def test_sync_check_live_stops_recording_when_dmd_runtime_raises(monkeypatch, tmp_path):
    from dmdcontrol.camera import sync_check

    events = []
    record_started = Event()
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        sync_check,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        sync_check,
        "_open_ready_camera",
        lambda run, args: (Mock(), Mock(), ready, None),
    )

    def fake_record(*args, **kwargs):
        events.append("record_start")
        record_started.set()
        stop_event = kwargs.get("stop_event")
        if stop_event is None:
            events.append("missing_stop_event")
            return SimpleNamespace(
                trigger_count=0,
                event_batch_count=0,
                trigger_batch_count=0,
                timed_out=False,
            )
        assert stop_event.wait(timeout=1.0)
        events.append("record_stop")
        return SimpleNamespace(
            trigger_count=0,
            event_batch_count=0,
            trigger_batch_count=0,
            timed_out=False,
        )

    monkeypatch.setattr(sync_check, "record_until_trigger_count", fake_record)

    def fake_run(pair_args, before_start):
        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})
        assert record_started.wait(timeout=1.0)
        raise RuntimeError("DMD runtime failed")

    monkeypatch.setattr(sync_check, "run_pair_runtime", fake_run)

    args = _parse_camera_args(
        sync_check,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
        ])

    try:
        sync_check.live(args)
    except RuntimeError as exc:
        assert str(exc) == "DMD runtime failed"
    else:
        raise AssertionError("live() should re-raise the DMD runtime failure")

    assert "record_stop" in events


def test_sync_check_live_writes_capture_artifacts_from_recorded_batches(monkeypatch, tmp_path):
    from dmdcontrol.camera import sync_check

    artifact_call = {}
    record_kwargs = {}
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )

    monkeypatch.setattr(
        sync_check,
        "create_run_directory",
        lambda *a, **k: _fake_run_directory(tmp_path),
    )
    monkeypatch.setattr(
        sync_check,
        "_open_ready_camera",
        lambda run, args: (Mock(), Mock(), ready, None),
    )

    startup_leader = _startup_leader()
    display_sequence = {
        "startup_policy": "blank_leader",
        "lut_slots_per_source_frame": 4,
    }

    def fake_run(pair_args, before_start):
        before_start(
            {
                "state_a": {
                    "timing": {}},
                "state_b": {
                    "timing": {}},
                "startup_leader": startup_leader,
                "display_sequence": display_sequence,
            })

    monkeypatch.setattr(sync_check, "run_pair_runtime", fake_run)

    def fake_record(*args, **kwargs):
        record_kwargs.update(kwargs)
        kwargs["on_events"]([{"timestamp": 105, "x": 2, "y": 1, "polarity": True}])
        kwargs["on_triggers"]([{"timestamp": 100, "edge": "rising"}])
        return SimpleNamespace(
            trigger_count=1,
            event_batch_count=1,
            trigger_batch_count=1,
            timed_out=False,
        )

    monkeypatch.setattr(sync_check, "record_until_trigger_count", fake_record)

    def fake_write_capture_artifacts(run, **kwargs):
        artifact_call.update(kwargs)
        return {
            "actual_trigger_count": len(kwargs["triggers"]),
            "frame_artifacts": ["accumulated_001.png"],
        }

    monkeypatch.setattr(sync_check, "write_capture_artifacts", fake_write_capture_artifacts)

    args = _parse_camera_args(
        sync_check,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
            "--count-end",
            "24",
            "--exposure-us",
            "600",
            "--event-noise-filter",
            "local-support",
            "--event-filter-delta-us",
            "50000",
            "--event-filter-window-px",
            "3",
            "--event-filter-threshold",
            "2",
            "--event-filter-polarity",
            "same",
        ])

    assert sync_check.live(args) == 0
    assert record_kwargs["expected_trigger_count"] is None
    assert artifact_call["events"] == [{"timestamp": 105, "x": 2, "y": 1, "polarity": True}]
    assert artifact_call["triggers"] == [{"timestamp": 100, "edge": "rising"}]
    assert artifact_call["resolution"] == (320, 240)
    assert artifact_call["window_us"] == 600
    assert artifact_call["startup_leader_trigger_count"] == 8
    assert artifact_call["event_noise_filter"].enabled is True
    assert artifact_call["event_noise_filter"].delta_t_us == 50000
    assert artifact_call["event_noise_filter"].window_px == 3
    assert artifact_call["event_noise_filter"].threshold == 2
    assert artifact_call["event_noise_filter"].polarity == "same"
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "sync-check"
    assert metadata["test"] == "a-count-b-static"
    assert metadata["test_b"] == "dot"
    assert metadata["count_start"] == 1
    assert metadata["count_end"] == 24
    assert metadata["count_slots_per_frame"] == 24
    assert metadata["count_slots_per_frame_mode"] == "auto"
    assert metadata["count_blank_between_frames"] is False
    assert metadata["exposure_us"] == 600
    assert metadata["expected_trigger_count"] == 24
    assert metadata["accumulation_window_us"] == 600
    assert metadata["bitplane_count"] == 24
    assert metadata["trigger_policy"] == {
        "channel": "TRIG_OUT_2",
        "source_dmd": "A",
        "edge": "rising",
        "rising_delay_us": 0,
        "falling_delay_us": 20,
    }
    assert metadata["event_noise_filter"]["enabled"] is True
    assert metadata["event_noise_filter"]["delta_t_us"] == 50000
    assert metadata["startup_leader"] == startup_leader
    assert metadata["display_sequence"] == display_sequence


def test_sync_check_live_capture_flushes_stale_batches_immediately_before_recording(
        monkeypatch,
        tmp_path):
    from dmdcontrol.camera import sync_check

    events = []
    record_started = Event()
    ready = SimpleNamespace(
        event_resolution=(320,
                          240),
        event_stream_available=True,
        trigger_stream_available=True,
    )
    capture = Mock()
    writer = Mock()

    def fake_flush(opened_capture, reads, include_triggers=True):
        assert opened_capture is capture
        events.append(("flush", reads, include_triggers))
        return {
            "requested_reads": reads,
            "event_reads": 1,
            "trigger_reads": 0,
            "event_batches_discarded": 0,
            "trigger_batches_discarded": 0,
            "event_count_discarded": 0,
            "trigger_count_discarded": 0,
            "stopped_early": True,
        }

    monkeypatch.setattr(sync_check, "flush_stale_batches", fake_flush)

    def fake_record(*args, **kwargs):
        events.append("record_start")
        record_started.set()
        return SimpleNamespace(
            trigger_count=0,
            event_batch_count=0,
            trigger_batch_count=0,
            timed_out=False,
        )

    monkeypatch.setattr(sync_check, "record_until_trigger_count", fake_record)

    def fake_run(pair_args, before_start):
        events.append("before_start")
        before_start({"state_a": {"timing": {}}, "state_b": {"timing": {}}})
        assert record_started.wait(timeout=1.0)
        events.append("sequencer_start_continued")

    monkeypatch.setattr(sync_check, "run_pair_runtime", fake_run)
    monkeypatch.setattr(sync_check, "write_capture_artifacts", lambda *args, **kwargs: {})

    args = _parse_camera_args(
        sync_check,
        [
            "--output-root",
            str(tmp_path),
            "--runtime-seconds",
            "1",
            "--camera-flush-reads",
            "7",
        ])
    run = _fake_run_directory(tmp_path)

    assert sync_check.live_capture(args, run, capture, writer, ready) == 0
    assert events == [
        "before_start",
        ("flush",
         7,
         True),
        "record_start",
        "sequencer_start_continued",
    ]
    metadata = __import__("json").loads(run.metadata_path.read_text(encoding="utf-8"))
    assert metadata["camera_pre_capture_flush"] == {
        "requested_reads": 7,
        "event_reads": 1,
        "trigger_reads": 0,
        "event_batches_discarded": 0,
        "trigger_batches_discarded": 0,
        "event_count_discarded": 0,
        "trigger_count_discarded": 0,
        "stopped_early": True,
    }
