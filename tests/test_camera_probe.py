import subprocess
import sys
from pathlib import Path

from debug_scripts import camera_probe


ROOT = Path(__file__).resolve().parents[1]


def test_camera_probe_accepts_duration_seconds():
    args = camera_probe.build_parser().parse_args(["--duration-seconds", "10"])

    assert args.duration_seconds == 10.0


def test_camera_probe_rejects_non_positive_duration():
    try:
        camera_probe.build_parser().parse_args(["--duration-seconds", "0"])
    except SystemExit:
        return

    raise AssertionError("duration must be positive")


def test_camera_probe_help_works_when_run_as_script():
    result = subprocess.run(
        [sys.executable, "debug_scripts/camera_probe.py", "--help"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--duration-seconds" in result.stdout
