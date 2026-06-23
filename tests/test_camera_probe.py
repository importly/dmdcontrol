import subprocess
import sys
from pathlib import Path

from debug_scripts import camera_probe

ROOT = Path(__file__).resolve().parents[1]


def test_camera_probe_accepts_duration_seconds():
    args = camera_probe.build_parser().parse_args(["--duration-seconds", "10"])

    assert args.duration_seconds == 10.0


def test_camera_probe_does_not_rearm_event_stream_by_default():
    args = camera_probe.build_parser().parse_args([])

    assert args.stream_rearm is False


def test_camera_probe_rejects_non_positive_duration():
    try:
        camera_probe.build_parser().parse_args(["--duration-seconds", "0"])
    except SystemExit:
        return

    raise AssertionError("duration must be positive")


def test_camera_probe_rearms_event_stream_before_capture(monkeypatch):
    calls = []

    class Capture:

        def setEventsRunning(self, value):
            calls.append(("events", value))

        def getNextEventBatch(self):
            calls.append(("read-events", None))
            return None

    monkeypatch.setattr(camera_probe.time, "sleep", lambda seconds: None)

    camera_probe.rearm_event_stream(Capture(), settle_s=0.01, drain_reads=2)

    assert calls == [
        ("events",
         False),
        ("events",
         True),
        ("read-events",
         None),
        ("read-events",
         None),
    ]


def test_camera_probe_help_works_when_run_as_script():
    result = subprocess.run(
        [sys.executable,
         "debug_scripts/camera_probe.py",
         "--help"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--duration-seconds" in result.stdout
