import json
import subprocess
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

from dmdcontrol.cli.main import main


def test_single_run_delegates_passthrough_args(monkeypatch):
    legacy = SimpleNamespace(main=Mock(return_value=7))
    monkeypatch.setitem(sys.modules, "main", legacy)

    assert main(["single", "run", "--test", "checkerboard"]) == 7

    legacy.main.assert_called_once_with(["--test", "checkerboard"])


def test_pair_run_translates_preferred_flags(monkeypatch):
    legacy = SimpleNamespace(main=Mock(return_value=0))
    monkeypatch.setitem(sys.modules, "main_pair", legacy)

    assert main(
        [
            "pair",
            "run",
            "--mode",
            "coarse-grid",
            "--b-test=dot",
            "--mode=checkerboard",
            "--b-test",
            "black",
        ]
    ) == 0

    legacy.main.assert_called_once_with(
        [
            "--test",
            "coarse-grid",
            "--test-b=dot",
            "--test=checkerboard",
            "--test-b",
            "black",
        ]
    )


def test_pair_calibrate_injects_test_and_default_zero_runtime(monkeypatch):
    legacy = SimpleNamespace(main=Mock(return_value=0))
    monkeypatch.setitem(sys.modules, "main_pair", legacy)

    assert main(["pair", "calibrate", "--b-dot-x", "10"]) == 0

    legacy.main.assert_called_once_with(
        [
            "--test",
            "a-calibr-square-b-dot",
            "--runtime-seconds",
            "0",
            "--b-dot-x",
            "10",
        ]
    )


def test_pair_calibrate_preserves_user_runtime_seconds(monkeypatch):
    legacy = SimpleNamespace(main=Mock(return_value=0))
    monkeypatch.setitem(sys.modules, "main_pair", legacy)

    assert main(["pair", "calibrate", "--runtime-seconds=5"]) == 0

    legacy.main.assert_called_once_with(
        ["--test", "a-calibr-square-b-dot", "--runtime-seconds=5"]
    )


def test_preview_serve_help_exits_zero(capsys):
    try:
        main(["preview", "serve", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("preview serve --help should exit through argparse")

    assert "Serve DMD bitplane preview UI" in capsys.readouterr().out


def test_usb_and_flood_commands_delegate_passthrough(monkeypatch):
    usb = SimpleNamespace(main=Mock(return_value=3))
    wake = SimpleNamespace(main=Mock(return_value=4))
    flood = SimpleNamespace(main=Mock(return_value=5))
    monkeypatch.setitem(sys.modules, "dmd_usb", usb)
    monkeypatch.setitem(sys.modules, "wake_dp", wake)
    monkeypatch.setitem(sys.modules, "flood_white_usb", flood)

    assert main(["usb", "discover", "--verbose"]) == 3
    assert main(["usb", "wake", "--dmd", "A"]) == 4
    assert main(["flood", "run", "--yes"]) == 5

    usb.main.assert_called_once_with(["--verbose"])
    wake.main.assert_called_once_with(["--dmd", "A"])
    flood.main.assert_called_once_with(["--yes"])


@dataclass(frozen=True)
class Mapping:
    name: str = "A"
    usb_id_path: str = "pci-0000:00"
    usb_devpath_contains: str | None = None
    xrandr_output: str | None = "DP-2"
    glfw_monitor_index: int | None = 1
    target_hz: int | None = 60


def test_config_show_prints_json(monkeypatch, capsys):
    resolver = Mock(return_value=Mapping())
    monkeypatch.setattr("dmdcontrol.cli.config.dmd_config.resolve_dmd_mapping", resolver)

    assert main(["config", "show", "--dmd", "A"]) == 0

    resolver.assert_called_once_with("A", None)
    assert json.loads(capsys.readouterr().out) == {
        "name": "A",
        "usb_id_path": "pci-0000:00",
        "usb_devpath_contains": None,
        "xrandr_output": "DP-2",
        "glfw_monitor_index": 1,
        "target_hz": 60,
    }


def test_config_show_prints_one_field(monkeypatch, capsys):
    resolver = Mock(return_value=Mapping())
    monkeypatch.setattr("dmdcontrol.cli.config.dmd_config.resolve_dmd_mapping", resolver)

    assert main(["config", "show", "--dmd", "A", "--field", "xrandr_output"]) == 0

    assert capsys.readouterr().out == "DP-2\n"


def test_module_preview_help_subprocess_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "dmdcontrol", "preview", "serve", "--help"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0
    assert "Serve DMD bitplane preview UI" in result.stdout
