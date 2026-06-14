import json
import sys
from types import SimpleNamespace

import numpy as np

from debug_scripts import persistent_camera_liveness_official


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
            FakeBatch(2,
                      100,
                      120),
            FakeBatch(3,
                      200,
                      230),
            FakeBatch(4,
                      400,
                      450),
        ]
        self.threshold_on = None
        self.threshold_off = None

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


class FakeAccumulator:
    created = []

    class Decay:
        EXPONENTIAL = "EXPONENTIAL"
        LINEAR = "LINEAR"
        STEP = "STEP"
        NONE = "NONE"

    def __init__(self, resolution):
        self.resolution = tuple(resolution)
        self.accepted_events = 0
        self.settings = []
        FakeAccumulator.created.append(self)

    def setEventContribution(self, value):
        self.settings.append(("event_contribution", value))

    def setNeutralPotential(self, value):
        self.settings.append(("neutral_potential", value))

    def setMinPotential(self, value):
        self.settings.append(("min_potential", value))

    def setMaxPotential(self, value):
        self.settings.append(("max_potential", value))

    def setDecayFunction(self, value):
        self.settings.append(("decay_function", value))

    def setDecayParam(self, value):
        self.settings.append(("decay_param", value))

    def setSynchronousDecay(self, value):
        self.settings.append(("synchronous_decay", value))

    def setIgnorePolarity(self, value):
        self.settings.append(("ignore_polarity", value))

    def accept(self, events):
        self.accepted_events += len(events)

    def generateFrame(self):
        width, height = self.resolution
        image = np.zeros((height, width), dtype=np.uint8)
        image[0, 0] = min(255, self.accepted_events * 20)
        return SimpleNamespace(image=image)


class FakeSlicer:

    def doEveryTimeInterval(self, interval, callback):
        self.interval = interval
        self.callback = callback

    def accept(self, events):
        self.callback(events)


def test_official_parser_defaults_match_reference_style():
    args = persistent_camera_liveness_official.build_parser().parse_args([])

    assert args.windows == 5
    assert args.duration_seconds == 2.0
    assert args.slice_ms == 33.0
    assert args.event_contribution == 0.25
    assert args.neutral_potential == 0.5
    assert args.decay_function == "LINEAR"
    assert args.ignore_polarity is False


def test_official_liveness_uses_one_open_and_writes_accumulator_pngs(tmp_path, monkeypatch):
    camera = FakeCamera()
    opens = []
    FakeAccumulator.created = []

    fake_dv = SimpleNamespace(
        __version__="fake",
        __file__="fake-dv.py",
        Accumulator=FakeAccumulator,
        EventStreamSlicer=FakeSlicer,
        io=SimpleNamespace(camera=SimpleNamespace(open=lambda: opens.append("open") or camera,
                                                  )),
    )

    monkeypatch.setitem(sys.modules, "dv_processing", fake_dv)
    monkeypatch.setattr(persistent_camera_liveness_official.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        persistent_camera_liveness_official,
        "_monotonic_seconds",
        _fake_clock([0.0,
                     0.1,
                     0.2,
                     0.6,
                     0.7,
                     0.8,
                     1.3]),
    )

    result = persistent_camera_liveness_official.run(
        [
            "--output-root",
            str(tmp_path),
            "--name",
            "official_same_handle",
            "--windows",
            "2",
            "--duration-seconds",
            "0.5",
            "--gap-seconds",
            "0.1",
            "--set-dvxplorer-defaults",
            "--ignore-polarity",
        ])

    assert result == 0
    assert opens == ["open"]
    assert camera.threshold_on == 9
    assert camera.threshold_off == 9
    assert len(FakeAccumulator.created) == 2
    assert ("ignore_polarity", True) in FakeAccumulator.created[0].settings

    out_dir = tmp_path / "official_same_handle"
    stats = json.loads((out_dir / "stats.json").read_text(encoding="utf-8"))
    assert stats["summary"]["camera_opens"] == 1
    assert [row["label"] for row in stats["windows"]] == [
        "window_01_official_accumulator",
        "window_02_official_accumulator",
    ]
    assert stats["windows"][0]["events"] == 5
    assert stats["windows"][1]["events"] == 4

    final_png = out_dir / "window_01_official_accumulator_final.png"
    assert final_png.exists()
    assert final_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert stats["windows"][0]["final_png"] == str(final_png)


def _fake_clock(values):
    values = list(values)
    last = values[-1]

    def now():
        if values:
            return values.pop(0)
        return last

    return now
