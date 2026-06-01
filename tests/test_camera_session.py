import sys
from types import SimpleNamespace


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


class FakeWriter:
    def __init__(self, path, capture):
        self.path = path
        self.capture = capture


def _args(**overrides):
    values = {
        "camera_power_cycle_command": None,
        "camera_usb_reset": False,
        "camera_stream_rearm": False,
        "camera_shutdown_streams": False,
        "camera_open_method": "modern",
        "bias_sensitivity": "default",
        "efps": "default",
        "camera_flush_reads": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_open_ready_camera_applies_shared_lifecycle(monkeypatch, tmp_path):
    from dmdcontrol.camera import session

    capture = FakeCapture()
    calls = []
    fake_dv = SimpleNamespace(
        io=SimpleNamespace(
            camera=SimpleNamespace(open=lambda: calls.append("open") or capture),
            MonoCameraWriter=FakeWriter,
        )
    )
    run = SimpleNamespace(raw_recording_path=tmp_path / "raw.aedat4")
    ready = SimpleNamespace(event_resolution=(320, 240))

    monkeypatch.setitem(sys.modules, "dv_processing", fake_dv)
    monkeypatch.setenv("DMD_CAMERA_POWER_CYCLE_COMMAND", "cycle-camera")
    monkeypatch.setattr(
        session,
        "run_power_cycle_command",
        lambda command: calls.append(("power", command)) or {"command": command},
    )
    monkeypatch.setattr(
        session,
        "reset_camera_usb",
        lambda dv, enabled: calls.append(("reset", dv is fake_dv, enabled)) or {"enabled": enabled},
    )
    monkeypatch.setattr(
        session,
        "rearm_camera_streams",
        lambda opened_capture: calls.append(("rearm", opened_capture is capture)) or {"rearmed": True},
    )
    monkeypatch.setattr(
        session,
        "configure_camera_performance",
        lambda opened_capture, bias_sensitivity, efps, prefer_legacy: calls.append(
            ("performance", opened_capture is capture, bias_sensitivity, efps, prefer_legacy)
        ),
    )
    monkeypatch.setattr(
        session,
        "configure_rising_edge_triggers",
        lambda opened_capture: calls.append(("triggers", opened_capture is capture)),
    )
    monkeypatch.setattr(
        session,
        "validate_camera_ready",
        lambda opened_capture, stream_rearm, usb_reset, power_cycle: calls.append(
            (
                "ready",
                opened_capture is capture,
                stream_rearm,
                usb_reset,
                power_cycle,
            )
        ) or ready,
    )

    opened_capture, writer, opened_ready = session.open_ready_camera(
        run,
        _args(
            camera_usb_reset=True,
            camera_stream_rearm=True,
            bias_sensitivity="low",
            efps="variable_5000",
            camera_flush_reads=2,
        ),
    )

    assert opened_capture is capture
    assert isinstance(writer, FakeWriter)
    assert writer.path == str(run.raw_recording_path)
    assert writer.capture is capture
    assert opened_ready is ready
    assert capture.event_reads == 2
    assert capture.trigger_reads == 2
    assert calls == [
        ("power", "cycle-camera"),
        ("reset", True, True),
        "open",
        ("rearm", True),
        ("performance", True, "low", "variable_5000", False),
        ("triggers", True),
        (
            "ready",
            True,
            {"rearmed": True},
            {"enabled": True},
            {"command": "cycle-camera"},
        ),
    ]


def test_open_ready_camera_cleans_up_when_flush_fails(monkeypatch, tmp_path):
    from dmdcontrol.camera import session

    capture = FakeCapture()
    calls = []
    writers = []

    class RecordingWriter(FakeWriter):
        def __init__(self, path, capture):
            super().__init__(path, capture)
            writers.append(self)

    fake_dv = SimpleNamespace(
        io=SimpleNamespace(
            camera=SimpleNamespace(open=lambda: capture),
            MonoCameraWriter=RecordingWriter,
        )
    )
    run = SimpleNamespace(raw_recording_path=tmp_path / "raw.aedat4")

    monkeypatch.setitem(sys.modules, "dv_processing", fake_dv)
    monkeypatch.setattr(session, "run_power_cycle_command", lambda command: None)
    monkeypatch.setattr(session, "reset_camera_usb", lambda dv, enabled: None)
    monkeypatch.setattr(session, "configure_camera_performance", lambda *args, **kwargs: None)
    monkeypatch.setattr(session, "configure_rising_edge_triggers", lambda *args, **kwargs: None)
    monkeypatch.setattr(session, "validate_camera_ready", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(
        session,
        "flush_stale_batches",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad flush")),
    )
    monkeypatch.setattr(
        session,
        "shutdown_camera_streams",
        lambda opened_capture: calls.append(("shutdown", opened_capture is capture)),
    )
    monkeypatch.setattr(session.gc, "collect", lambda: calls.append("gc"))

    try:
        session.open_ready_camera(
            run,
            _args(camera_shutdown_streams=True),
        )
    except RuntimeError as exc:
        assert str(exc) == "bad flush"
    else:
        raise AssertionError("expected camera setup failure")

    assert len(writers) == 1
    assert writers[0].path == str(run.raw_recording_path)
    assert writers[0].capture is capture
    assert calls == [("shutdown", True), "gc"]


def test_close_camera_resources_empties_holder_before_gc(monkeypatch, tmp_path):
    from dmdcontrol.camera import session

    capture = FakeCapture()
    writer = FakeWriter(str(tmp_path / "raw.aedat4"), capture)
    resources = {"writer": writer, "capture": capture}
    calls = []

    monkeypatch.setattr(
        session,
        "shutdown_camera_streams",
        lambda opened_capture: calls.append(("shutdown", opened_capture is capture)),
    )

    def collect():
        assert resources == {}
        calls.append("gc")

    monkeypatch.setattr(session.gc, "collect", collect)

    session.close_camera_resources(resources, shutdown_streams=True)

    assert resources == {}
    assert calls == [("shutdown", True), "gc"]


def test_close_camera_resources_skips_optional_stream_shutdown(monkeypatch, tmp_path):
    from dmdcontrol.camera import session

    capture = FakeCapture()
    writer = FakeWriter(str(tmp_path / "raw.aedat4"), capture)
    resources = {"writer": writer, "capture": capture}
    calls = []

    monkeypatch.setattr(
        session,
        "shutdown_camera_streams",
        lambda opened_capture: calls.append(("shutdown", opened_capture is capture)),
    )
    monkeypatch.setattr(session.gc, "collect", lambda: calls.append("gc"))

    session.close_camera_resources(resources, shutdown_streams=False)

    assert resources == {}
    assert calls == ["gc"]


def test_open_ready_camera_can_use_legacy_camera_open_method(monkeypatch, tmp_path):
    from dmdcontrol.camera import session

    capture = FakeCapture()
    calls = []
    fake_dv = SimpleNamespace(io=SimpleNamespace(MonoCameraWriter=FakeWriter))
    run = SimpleNamespace(raw_recording_path=tmp_path / "raw.aedat4")

    monkeypatch.setitem(sys.modules, "dv_processing", fake_dv)
    monkeypatch.setattr(session, "run_power_cycle_command", lambda command: None)
    monkeypatch.setattr(session, "reset_camera_usb", lambda dv, enabled: None)
    monkeypatch.setattr(
        session,
        "open_camera_capture",
        lambda dv, method: calls.append(("open", dv is fake_dv, method)) or capture,
    )
    monkeypatch.setattr(
        session,
        "configure_camera_performance",
        lambda opened_capture, bias_sensitivity, efps, prefer_legacy: calls.append(
            ("performance", opened_capture is capture, bias_sensitivity, efps, prefer_legacy)
        ),
    )
    monkeypatch.setattr(session, "configure_rising_edge_triggers", lambda *args, **kwargs: None)
    monkeypatch.setattr(session, "validate_camera_ready", lambda *args, **kwargs: SimpleNamespace())

    session.open_ready_camera(
        run,
        _args(
            camera_open_method="legacy",
            bias_sensitivity="low",
            efps="variable_5000",
        ),
    )

    assert calls == [
        ("open", True, "legacy"),
        ("performance", True, "low", "variable_5000", True),
    ]
