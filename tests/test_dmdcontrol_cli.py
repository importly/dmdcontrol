import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock


def run_cli(argv):
    from dmdcontrol.cli.main import main

    return main(argv)


def test_cli_main_import_does_not_load_hardware_modules():
    for name in (
        "usb.core",
        "dmdcontrol.hardware.flood",
        "dmdcontrol.hardware.usb",
        "dmdcontrol.hardware.wake",
        "dmdcontrol.hardware.dlpc900",
    ):
        sys.modules.pop(name, None)
    for name in [name for name in sys.modules if name.startswith("dmdcontrol.cli")]:
        sys.modules.pop(name, None)
    hardware_package = sys.modules.get("dmdcontrol.hardware")
    if hardware_package is not None:
        for attribute in ("dlpc900", "flood", "usb", "wake"):
            vars(hardware_package).pop(attribute, None)

    importlib.import_module("dmdcontrol.cli.main")

    assert "usb.core" not in sys.modules
    assert "dmdcontrol.hardware.flood" not in sys.modules
    assert "dmdcontrol.hardware.usb" not in sys.modules
    assert "dmdcontrol.hardware.wake" not in sys.modules
    assert "dmdcontrol.hardware.dlpc900" not in sys.modules


def test_single_run_delegates_passthrough_args(monkeypatch):
    runtime = Mock(return_value=7)
    monkeypatch.setattr(
        "dmdcontrol.cli.single._single_runtime",
        lambda: SimpleNamespace(main=runtime),
    )

    assert run_cli(["single", "run", "--test", "checkerboard"]) == 7

    runtime.assert_called_once_with(["--test", "checkerboard"])


def test_pair_run_translates_preferred_flags(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr(
        "dmdcontrol.cli.pair._pair_runtime",
        lambda: SimpleNamespace(main=runtime),
    )

    assert run_cli(
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

    runtime.assert_called_once_with(
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
    runtime = Mock(return_value=0)
    monkeypatch.setattr(
        "dmdcontrol.cli.pair._pair_runtime",
        lambda: SimpleNamespace(main=runtime),
    )

    assert run_cli(["pair", "calibrate", "--b-dot-x", "10"]) == 0

    runtime.assert_called_once_with(
        [
            "--test",
            "a-calibr-square-b-dot",
            "--runtime-seconds",
            "0",
            "--b-dot-x",
            "10",
        ]
    )


def test_pair_calibrate_preserves_essential_preview_dot_args(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr(
        "dmdcontrol.cli.pair._pair_runtime",
        lambda: SimpleNamespace(main=runtime),
    )

    assert (
        run_cli(
            [
                "pair",
                "calibrate",
                "--b-dot-x",
                "960",
                "--b-dot-y",
                "540",
                "--b-dot-radius",
                "40",
                "--preview-url",
                "http://127.0.0.1:8080/api/live-frame",
                "--preview-fps",
                "1",
            ]
        )
        == 0
    )

    runtime.assert_called_once_with(
        [
            "--test",
            "a-calibr-square-b-dot",
            "--runtime-seconds",
            "0",
            "--b-dot-x",
            "960",
            "--b-dot-y",
            "540",
            "--b-dot-radius",
            "40",
            "--preview-url",
            "http://127.0.0.1:8080/api/live-frame",
            "--preview-fps",
            "1",
        ]
    )


def test_pair_calibrate_preserves_user_runtime_seconds(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr(
        "dmdcontrol.cli.pair._pair_runtime",
        lambda: SimpleNamespace(main=runtime),
    )

    assert run_cli(["pair", "calibrate", "--runtime-seconds=5"]) == 0

    runtime.assert_called_once_with(
        ["--test", "a-calibr-square-b-dot", "--runtime-seconds=5"]
    )


def test_preview_serve_help_exits_zero(capsys):
    try:
        run_cli(["preview", "serve", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("preview serve --help should exit through argparse")

    assert "Serve DMD bitplane preview UI" in capsys.readouterr().out


def test_usb_and_flood_commands_delegate_passthrough(monkeypatch):
    usb = Mock(return_value=3)
    wake = Mock(return_value=4)
    flood = Mock(return_value=5)
    monkeypatch.setattr("dmdcontrol.cli.usb._usb_module", lambda: SimpleNamespace(main=usb))
    monkeypatch.setattr("dmdcontrol.cli.usb._wake_module", lambda: SimpleNamespace(main=wake))
    monkeypatch.setattr(
        "dmdcontrol.cli.flood._flood_module",
        lambda: SimpleNamespace(main=flood),
    )

    assert run_cli(["usb", "discover", "--verbose"]) == 3
    assert run_cli(["usb", "wake", "--dmd", "A"]) == 4
    assert run_cli(["flood", "run", "--yes"]) == 5

    usb.assert_called_once_with(["--verbose"])
    wake.assert_called_once_with(["--dmd", "A"])
    flood.assert_called_once_with(["--yes"])


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
    monkeypatch.setattr(
        "dmdcontrol.cli.config._mapping_module",
        lambda: SimpleNamespace(resolve_dmd_mapping=resolver),
    )

    assert run_cli(["config", "show", "--dmd", "A"]) == 0

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
    monkeypatch.setattr(
        "dmdcontrol.cli.config._mapping_module",
        lambda: SimpleNamespace(resolve_dmd_mapping=resolver),
    )

    assert run_cli(["config", "show", "--dmd", "A", "--field", "xrandr_output"]) == 0

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
