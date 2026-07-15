from types import SimpleNamespace

from dmdcontrol.camera import discovery


class ModernDVXplorerCapture:
    def __init__(self):
        self.thresholds = []
        self.readout_fps = []
        self.global_hold = []

    def setContrastThresholdOn(self, value):
        self.thresholds.append(("on", value))

    def setContrastThresholdOff(self, value):
        self.thresholds.append(("off", value))

    def setReadoutFPS(self, value):
        self.readout_fps.append(value)

    def setGlobalHold(self, value):
        self.global_hold.append(value)


class ResettableCapture:
    def __init__(self):
        self.calls = []
        self.event_batches = ["stale-event", None]
        self.trigger_batches = ["stale-trigger", None]

    def setEventsRunning(self, value):
        self.calls.append(("events", value))

    def setDetectorRunning(self, value):
        self.calls.append(("detector", value))

    def setGeneratorRunning(self, value):
        self.calls.append(("generator", value))

    def getNextEventBatch(self):
        self.calls.append(("read-events", None))
        return self.event_batches.pop(0) if self.event_batches else None

    def getNextTriggerBatch(self):
        self.calls.append(("read-triggers", None))
        return self.trigger_batches.pop(0) if self.trigger_batches else None


def test_rearm_camera_streams_cycles_events_and_drains_stale_batches(monkeypatch):
    capture = ResettableCapture()
    monkeypatch.setattr(discovery.time, "sleep", lambda seconds: None)

    result = discovery.rearm_camera_streams(capture, settle_s=0.01, drain_reads=2)

    assert result == {
        "stopped_events": True,
        "stopped_detector": True,
        "stopped_generator": True,
        "started_events": True,
        "drain_reads": 2,
    }
    assert capture.calls == [
        ("events", False),
        ("detector", False),
        ("generator", False),
        ("events", True),
        ("read-events", None),
        ("read-triggers", None),
        ("read-events", None),
        ("read-triggers", None),
    ]


def test_shutdown_camera_streams_stops_available_streams():
    capture = ResettableCapture()

    result = discovery.shutdown_camera_streams(capture)

    assert result == {
        "stopped_events": True,
        "stopped_detector": True,
        "stopped_generator": True,
        "errors": [],
    }
    assert capture.calls[:3] == [
        ("events", False),
        ("detector", False),
        ("generator", False),
    ]


def test_shutdown_camera_streams_reports_stop_errors_without_raising():

    class Capture:
        def setEventsRunning(self, value):
            raise RuntimeError("camera gone")

    result = discovery.shutdown_camera_streams(Capture())

    assert result["stopped_events"] is False
    assert "camera gone" in result["errors"][0]


def test_configure_rising_edge_triggers_restarts_detector_and_reports_calls():

    class Capture:
        def __init__(self):
            self.calls = []

        def setDetectorRunning(self, value):
            self.calls.append(("running", value))

        def setDetectorRisingEdges(self, value):
            self.calls.append(("rising", value))

        def setDetectorFallingEdges(self, value):
            self.calls.append(("falling", value))

    capture = Capture()

    result = discovery.configure_rising_edge_triggers(capture)

    assert capture.calls == [
        ("running", False),
        ("rising", True),
        ("falling", False),
        ("running", True),
    ]
    assert result["has_setDetectorRunning"] is True
    assert result["has_setDetectorRisingEdges"] is True
    assert result["has_setDetectorFallingEdges"] is True
    assert result["call_order"] == [
        "setDetectorRunning(False)",
        "setDetectorRisingEdges(True)",
        "setDetectorFallingEdges(False)",
        "setDetectorRunning(True)",
    ]
    assert result["setDetectorRunning_false_error"] is None
    assert result["setDetectorRunning_true_error"] is None
    assert result["errors"] == []


def test_configure_rising_edge_triggers_records_errors_without_raising():

    class Capture:
        def setDetectorRunning(self, value):
            if value is True:
                raise RuntimeError("detector would not start")

        def setDetectorRisingEdges(self, value):
            return None

    result = discovery.configure_rising_edge_triggers(Capture())

    assert result["has_setDetectorRunning"] is True
    assert result["has_setDetectorRisingEdges"] is True
    assert result["has_setDetectorFallingEdges"] is False
    assert result["setDetectorRunning_true_result"] is None
    assert "detector would not start" in result["setDetectorRunning_true_error"]
    assert result["errors"] == [
        "setDetectorRunning(True): RuntimeError('detector would not start')"
    ]


def test_configure_camera_performance_uses_dvxplorer_contrast_thresholds(monkeypatch):
    capture = ModernDVXplorerCapture()
    import builtins

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "dv_processing":
            raise AssertionError("dv import not needed for thresholds")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    discovery.configure_camera_performance(capture, bias_sensitivity="veryhigh")

    assert capture.thresholds == [("on", 3), ("off", 3)]


def test_configure_camera_performance_uses_dvxplorer_readout_fps(monkeypatch):
    import sys

    capture = ModernDVXplorerCapture()
    readout = SimpleNamespace(VARIABLE_5000="variable-5000")
    dv = SimpleNamespace(
        io=SimpleNamespace(
            camera=SimpleNamespace(
                DVXplorer=SimpleNamespace(ReadoutFPS=readout),
            ),
        ),
    )
    monkeypatch.setitem(sys.modules, "dv_processing", dv)

    discovery.configure_camera_performance(capture, efps="variable_5000")

    assert capture.readout_fps == ["variable-5000"]


def test_configure_camera_performance_preserves_global_hold_by_default():
    capture = ModernDVXplorerCapture()

    result = discovery.configure_camera_performance(capture)

    assert capture.global_hold == []
    assert result["requested"]["global_hold"] == "default"
    assert result["applied"]["global_hold"] is False


def test_configure_camera_performance_changes_global_hold_only_when_requested():
    capture = ModernDVXplorerCapture()

    result = discovery.configure_camera_performance(capture, global_hold="off")

    assert capture.global_hold == [False]
    assert result["requested"]["global_hold"] == "off"
    assert result["applied"]["global_hold"] is True


def test_open_camera_capture_uses_current_camera_open_api():
    opened = object()
    dv = SimpleNamespace(
        io=SimpleNamespace(camera=SimpleNamespace(open=lambda: opened))
    )

    assert discovery.open_camera_capture(dv) is opened
