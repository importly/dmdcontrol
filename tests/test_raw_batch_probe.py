import sys
from types import SimpleNamespace

from debug_scripts import raw_batch_probe


class FakeBatch(list):

    def __init__(self, size, lo, hi):
        super().__init__(range(size))
        self.lo = lo
        self.hi = hi

    def getLowestTime(self):
        return self.lo

    def getHighestTime(self):
        return self.hi


class FakeCamera:

    def __init__(self):
        self.batches = [
            None,
            FakeBatch(2, 100, 120),
            FakeBatch(3, 200, 230),
        ]
        self.threshold_on = None
        self.threshold_off = None
        self.global_hold = None
        self.global_reset = None

    def getCameraName(self):
        return "FakeDVXplorer"

    def getEventResolution(self):
        return (8, 6)

    def getNextEventBatch(self):
        if self.batches:
            return self.batches.pop(0)
        return None

    def isRunning(self):
        return True

    def isEventStreamAvailable(self):
        return True

    def setContrastThresholdOn(self, value):
        self.threshold_on = value

    def setContrastThresholdOff(self, value):
        self.threshold_off = value

    def setGlobalHold(self, value):
        self.global_hold = value

    def setGlobalReset(self, value):
        self.global_reset = value


def test_raw_batch_probe_parser_aliases():
    args = raw_batch_probe.build_parser().parse_args(
        [
            "--duration-seconds",
            "4",
            "--gap-seconds",
            "0.5",
            "--set-dvxplorer-defaults",
            "--prestate",
            "physical_replug=yes",
        ])

    assert args.duration_seconds == 4
    assert args.gap_seconds == 0.5
    assert args.set_dvxplorer_defaults is True
    assert raw_batch_probe.parse_prestate(args.prestate) == {
        "fields": {
            "physical_replug": "yes",
        },
        "notes": [],
    }


def test_raw_batch_probe_reports_wall_bins_and_timestamp_span(monkeypatch):
    camera = FakeCamera()

    monkeypatch.setattr(raw_batch_probe.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(raw_batch_probe, "_monotonic_seconds", _fake_clock([0.0, 0.1, 0.2, 0.4, 0.6]))

    result = raw_batch_probe.capture_window(camera, "window_01", 0.5)

    assert result["events"] == 5
    assert result["batches"] == 2
    assert result["none_count"] == 1
    assert result["wall_second_event_bins"] == [5]
    assert result["first_ts"] == 100
    assert result["last_ts"] == 230
    assert result["camera_span_s"] == 0.00013


def test_raw_batch_probe_run_opens_once_and_applies_defaults(monkeypatch):
    camera = FakeCamera()
    opens = []

    fake_dv = SimpleNamespace(
        __version__="fake",
        __file__="fake-dv.py",
        io=SimpleNamespace(
            camera=SimpleNamespace(
                discover=lambda: [SimpleNamespace(serialNumber="DXBFAKE")],
                open=lambda: opens.append("open") or camera,
                DVXplorer=SimpleNamespace(ReadoutFPS=SimpleNamespace(VARIABLE_5000="VARIABLE_5000")),
            )),
    )

    monkeypatch.setitem(sys.modules, "dv_processing", fake_dv)
    monkeypatch.setattr(raw_batch_probe.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(raw_batch_probe, "_monotonic_seconds", _fake_clock([0.0, 0.1, 0.2]))

    result = raw_batch_probe.run(["--windows", "1", "--duration", "0.15", "--defaults"])

    assert result == 0
    assert opens == ["open"]
    assert camera.threshold_on == 9
    assert camera.threshold_off == 9
    assert camera.global_hold is True
    assert camera.global_reset is False


def _fake_clock(values):
    values = list(values)
    last = values[-1]

    def now():
        if values:
            return values.pop(0)
        return last

    return now
