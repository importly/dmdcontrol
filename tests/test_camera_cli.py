import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def run_cli(argv):
    from dmdcontrol.cli.main import main

    return main(argv)


def test_camera_help_import_does_not_load_dv_processing():
    sys.modules.pop("dv_processing", None)
    for name in [name for name in sys.modules if name.startswith("dmdcontrol.cli")]:
        sys.modules.pop(name, None)

    try:
        run_cli(["camera", "--help"])
    except SystemExit as exc:
        assert exc.code == 0

    assert "dv_processing" not in sys.modules


@pytest.mark.parametrize("command", ["sync-check", "pair-capture"])
def test_camera_subcommand_help_exits_zero_without_dv_processing(command):
    sys.modules.pop("dv_processing", None)

    with pytest.raises(SystemExit) as exc:
        run_cli(["camera", command, "--help"])

    assert exc.value.code == 0
    assert "dv_processing" not in sys.modules


def test_camera_discover_delegates(monkeypatch, capsys):
    discover = Mock(return_value=[{"index": 0, "cameraModel": "DVXPLORER"}])
    monkeypatch.setattr(
        "dmdcontrol.cli.camera._discovery_module",
        lambda: SimpleNamespace(discover_cameras=discover),
    )

    assert run_cli(["camera", "discover"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["cameraModel"] == "DVXPLORER"
