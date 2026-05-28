from types import SimpleNamespace

from dmdcontrol.camera import discovery


class ModernDVXplorerCapture:
    def __init__(self):
        self.thresholds = []
        self.readout_fps = []

    def setContrastThresholdOn(self, value):
        self.thresholds.append(("on", value))

    def setContrastThresholdOff(self, value):
        self.thresholds.append(("off", value))

    def setReadoutFPS(self, value):
        self.readout_fps.append(value)


def test_configure_camera_performance_uses_dvxplorer_contrast_thresholds(monkeypatch):
    capture = ModernDVXplorerCapture()
    monkeypatch.setattr(
        discovery,
        "import_dv_processing",
        lambda: (_ for _ in ()).throw(AssertionError("dv import not needed for thresholds")),
    )

    discovery.configure_camera_performance(capture, bias_sensitivity="veryhigh")

    assert capture.thresholds == [("on", 3), ("off", 3)]


def test_configure_camera_performance_uses_dvxplorer_readout_fps(monkeypatch):
    capture = ModernDVXplorerCapture()
    readout = SimpleNamespace(VARIABLE_5000="variable-5000")
    dv = SimpleNamespace(
        io=SimpleNamespace(
            camera=SimpleNamespace(
                DVXplorer=SimpleNamespace(ReadoutFPS=readout),
            ),
        ),
    )
    monkeypatch.setattr(discovery, "import_dv_processing", lambda: dv)

    discovery.configure_camera_performance(capture, efps="variable_5000")

    assert capture.readout_fps == ["variable-5000"]
