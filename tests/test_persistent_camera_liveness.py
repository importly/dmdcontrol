import json
import sys
from pathlib import Path
from types import SimpleNamespace

from debug_scripts import persistent_camera_liveness


class FakeEvent:

    def __init__(self, x, y, polarity, timestamp):
        self.x = x
        self.y = y
        self.polarity = polarity
        self.timestamp = timestamp


class FakeBatch(list):

    def getLowestTime(self):
        return min(event.timestamp for event in self)

    def getHighestTime(self):
        return max(event.timestamp for event in self)


class FakeCamera:

    def __init__(self):
        self.calls = []
        self.opened = True
        self.threshold_on = None
        self.threshold_off = None
        self.batches = [
            None,
            FakeBatch([FakeEvent(1,
                                 1,
                                 True,
                                 100),
                       FakeEvent(2,
                                 2,
                                 False,
                                 101)]),
            FakeBatch([FakeEvent(3,
                                 3,
                                 True,
                                 200)]),
            None,
            FakeBatch([FakeEvent(4,
                                 4,
                                 True,
                                 300)]),
        ]

    def getCameraName(self):
        return "FakeDVXplorer"

    def getEventResolution(self):
        return (8, 6)

    def getNextEventBatch(self):
        self.calls.append("read")
        if self.batches:
            return self.batches.pop(0)
        return None

    def setContrastThresholdOn(self, value):
        self.threshold_on = value

    def setContrastThresholdOff(self, value):
        self.threshold_off = value


def test_parser_defaults_to_multiple_same_handle_windows():
    args = persistent_camera_liveness.build_parser().parse_args([])

    assert args.windows == 5
    assert args.duration_seconds == 2.0
    assert args.gap_seconds == 1.0
    assert args.threshold == 9


def test_persistent_liveness_opens_once_and_writes_per_window_stats(tmp_path, monkeypatch):
    camera = FakeCamera()
    opens = []

    fake_dv = SimpleNamespace(
        __version__="fake",
        __file__="fake-dv.py",
        io=SimpleNamespace(
            camera=SimpleNamespace(
                discover=lambda: [SimpleNamespace(serialNumber="DXBFAKE")],
                open=lambda descriptor: opens.append(descriptor) or camera,
            )),
    )

    monkeypatch.setitem(sys.modules, "dv_processing", fake_dv)
    monkeypatch.setattr(persistent_camera_liveness.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        persistent_camera_liveness,
        "_monotonic_seconds",
        _fake_clock([0.0,
                     0.2,
                     0.5,
                     0.6,
                     0.9,
                     1.2,
                     1.3,
                     1.6,
                     1.9,
                     2.2]),
    )

    result = persistent_camera_liveness.run(
        [
            "--output-root",
            str(tmp_path),
            "--name",
            "same_handle",
            "--windows",
            "2",
            "--duration-seconds",
            "0.5",
            "--gap-seconds",
            "0.1",
        ])

    assert result == 0
    assert len(opens) == 1
    assert camera.threshold_on == 9
    assert camera.threshold_off == 9

    out_dir = tmp_path / "same_handle"
    stats = json.loads((out_dir / "stats.json").read_text(encoding="utf-8"))
    assert [row["label"] for row in stats["windows"]] == [
        "window_01_same_handle",
        "window_02_same_handle",
    ]
    assert stats["summary"]["camera_opens"] == 1
    assert stats["windows"][0]["events"] == 2
    assert stats["windows"][1]["events"] == 1
    assert (out_dir / "window_01_same_handle.pgm").exists()
    png_path = out_dir / "window_01_same_handle.png"
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert stats["windows"][0]["png"] == str(png_path)
    assert (out_dir / "window_02_same_handle.npy").exists()


def _fake_clock(values):
    values = list(values)
    last = values[-1]

    def now():
        if values:
            return values.pop(0)
        return last

    return now
