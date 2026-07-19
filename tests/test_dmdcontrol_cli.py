import ast
import importlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def run_cli(argv):
    from dmdcontrol.cli.main import main

    return main(argv)


def test_cli_main_import_does_not_load_hardware_modules():
    for name in (
            "usb.core",
            "dmdcontrol.hardware.usb",
            "dmdcontrol.hardware.dlpc900",
    ):
        sys.modules.pop(name, None)
    for name in [name for name in sys.modules if name.startswith("dmdcontrol.cli")]:
        sys.modules.pop(name, None)
    hardware_package = sys.modules.get("dmdcontrol.hardware")
    if hardware_package is not None:
        for attribute in ("dlpc900", "usb"):
            vars(hardware_package).pop(attribute, None)

    importlib.import_module("dmdcontrol.cli.main")

    assert "usb.core" not in sys.modules
    assert "dmdcontrol.hardware.usb" not in sys.modules
    assert "dmdcontrol.hardware.dlpc900" not in sys.modules


def test_production_code_uses_static_import_syntax():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in sorted((root / "dmdcontrol").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "importlib":
                if any(alias.name == "import_module" for alias in node.names):
                    offenders.append(path.relative_to(root).as_posix())
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if (isinstance(node.func.value,
                               ast.Name) and node.func.value.id == "importlib"
                        and node.func.attr == "import_module"):
                    offenders.append(path.relative_to(root).as_posix())

    assert offenders == []


def test_function_local_imports_are_limited_to_explicit_boundaries():
    root = Path(__file__).resolve().parents[1]
    allowed_targets = {
        "dmdcontrol/camera/discovery.py": {"dv_processing"},
        "dmdcontrol/camera/reprocess_aedat4.py": {"dv_processing"},
        "dmdcontrol/camera/session.py": {"dv_processing"},
        "dmdcontrol/cli/main.py": {"dmdcontrol.camera", "dmdcontrol.cli"},
        "dmdcontrol/patterns/calibration_square.py": {"glfw"},
        "dmdcontrol/patterns/paired.py": {"OpenGL.GL", "glfw"},
        "dmdcontrol/preview/__init__.py": {"dmdcontrol.preview"},
    }
    offenders = []
    for path in sorted((root / "dmdcontrol").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        relative_path = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            parent = parents.get(node)
            while parent is not None and not isinstance(
                    parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parent = parents.get(parent)
            if parent is None:
                continue
            targets = (
                [node.module]
                if isinstance(node, ast.ImportFrom)
                else [alias.name for alias in node.names]
            )
            for target in targets:
                if target not in allowed_targets.get(relative_path, set()):
                    offenders.append(f"{relative_path}:{parent.name}:{target}")

    assert offenders == []

def test_single_run_delegates_passthrough_args(monkeypatch):
    runtime = Mock(return_value=7)
    monkeypatch.setattr("dmdcontrol.cli.single.runtime_main", runtime)

    assert run_cli(["single", "run", "--test", "checkerboard"]) == 7

    runtime.assert_called_once_with(["--test", "checkerboard"])


def test_pair_run_translates_preferred_flags(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr("dmdcontrol.cli.pair.runtime_main", runtime)

    assert run_cli(
        [
            "pair",
            "run",
            "--mode",
            "grid",
            "--b-test=dot",
            "--mode=checkerboard",
            "--b-test",
            "black",
        ]) == 0

    runtime.assert_called_once_with(
        [
            "--test",
            "grid",
            "--test-b=dot",
            "--test=checkerboard",
            "--test-b",
            "black",
        ])


def test_pair_calibrate_injects_test_and_default_zero_runtime(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr("dmdcontrol.cli.pair.runtime_main", runtime)

    assert run_cli(["pair", "calibrate", "--b-dot-x", "10"]) == 0

    runtime.assert_called_once_with(
        [
            "--test",
            "a-calibr-square-b-dot",
            "--runtime-seconds",
            "0",
            "--b-dot-x",
            "10",
        ])


def test_pair_calibrate_preserves_essential_preview_dot_args(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr("dmdcontrol.cli.pair.runtime_main", runtime)

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
            ]) == 0)

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
        ])


def test_pair_calibrate_preserves_user_runtime_seconds(monkeypatch):
    runtime = Mock(return_value=0)
    monkeypatch.setattr("dmdcontrol.cli.pair.runtime_main", runtime)

    assert run_cli(["pair", "calibrate", "--runtime-seconds=5"]) == 0

    runtime.assert_called_once_with(["--test", "a-calibr-square-b-dot", "--runtime-seconds=5"])


def test_preview_serve_help_exits_zero(capsys):
    try:
        run_cli(["preview", "serve", "--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("preview serve --help should exit through argparse")

    assert "Serve DMD bitplane preview UI" in capsys.readouterr().out


def test_usb_discover_delegates_passthrough(monkeypatch):
    usb = Mock(return_value=3)
    monkeypatch.setattr("dmdcontrol.cli.usb_discover.usb_main", usb)

    assert run_cli(["usb", "discover", "--verbose"]) == 3

    usb.assert_called_once_with(["--verbose"])


def test_usb_wake_uses_direct_dependencies(monkeypatch):
    from dmdcontrol.cli import usb as usb_cli

    calls = []

    class FakeDLPC900:

        def __init__(self, usb_id_path=None, usb_devpath_contains=None):
            calls.append(("init", usb_id_path, usb_devpath_contains))

        def wake_displayport_receiver(self):
            calls.append(("wake",))

        def set_input_source(self, source, bit_depth_sel):
            calls.append(("input_source", source, bit_depth_sel))

        def set_display_mode(self, mode):
            calls.append(("display_mode", mode))

        def apply_block_lock_workaround(self):
            calls.append(("block_lock",))

    resolver = Mock(return_value=Mapping(name="A", usb_id_path="pci-0000:00", usb_devpath_contains="/usb1/1-1/"))
    setup_logger = Mock()
    logger = SimpleNamespace(info=Mock())
    monkeypatch.setattr(usb_cli, "DLPC900", FakeDLPC900)
    monkeypatch.setattr(usb_cli, "resolve_dmd_mapping", resolver)
    monkeypatch.setattr(usb_cli, "setup_logger", setup_logger)
    monkeypatch.setattr(usb_cli, "logger", logger)
    monkeypatch.setattr(usb_cli.time, "sleep", Mock())

    assert run_cli(["usb", "wake", "--dmd", "A", "--dmd-config", "devices.json"]) == 0

    resolver.assert_called_once_with("A", "devices.json")
    setup_logger.assert_called_once_with(verbose=False)
    assert calls == [
        ("init", "pci-0000:00", "/usb1/1-1/"),
        ("wake",),
        ("input_source", 0, 1),
        ("display_mode", 0),
        ("block_lock",),
    ]


def test_flood_command_is_removed():
    with pytest.raises(SystemExit) as excinfo:
        run_cli(["flood", "run", "--yes"])

    assert excinfo.value.code == 2


def test_camera_sync_sweep_command_is_removed():
    with pytest.raises(SystemExit) as excinfo:
        run_cli(["camera", "sync-sweep", "--manifest", "runs/sweep.csv"])

    assert excinfo.value.code == 2


@dataclass(frozen=True)
class Mapping:
    name: str = "A"
    usb_id_path: str = "pci-0000:00"
    usb_devpath_contains: str | None = None
    xrandr_output: str | None = "DP-2"
    glfw_monitor_index: int | None = 1


def test_config_show_prints_json(monkeypatch, capsys):
    resolver = Mock(return_value=Mapping())
    monkeypatch.setattr("dmdcontrol.cli.config.resolve_dmd_mapping", resolver)

    assert run_cli(["config", "show", "--dmd", "A"]) == 0

    resolver.assert_called_once_with("A", None)
    assert json.loads(capsys.readouterr().out) == {
        "name": "A",
        "usb_id_path": "pci-0000:00",
        "usb_devpath_contains": None,
        "xrandr_output": "DP-2",
        "glfw_monitor_index": 1,
    }


def test_config_show_prints_one_field(monkeypatch, capsys):
    resolver = Mock(return_value=Mapping())
    monkeypatch.setattr("dmdcontrol.cli.config.resolve_dmd_mapping", resolver)

    assert run_cli(["config", "show", "--dmd", "A", "--field", "xrandr_output"]) == 0

    assert capsys.readouterr().out == "DP-2\n"


def test_config_show_rejects_removed_target_hz_field():
    with pytest.raises(SystemExit) as excinfo:
        run_cli(["config", "show", "--dmd", "A", "--field", "target_hz"])

    assert excinfo.value.code == 2


def test_module_preview_help_subprocess_exits_zero():
    result = subprocess.run(
        [sys.executable,
         "-m",
         "dmdcontrol",
         "preview",
         "serve",
         "--help"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0
    assert "Serve DMD bitplane preview UI" in result.stdout
