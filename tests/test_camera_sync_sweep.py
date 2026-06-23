import csv
import json
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from dmdcontrol.camera import sync_sweep


def _write_manifest(path, rows):
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sync_check_argv(tmp_path, timestamp, exposure, rising_delay_us):
    return [
        "--output-root",
        str(tmp_path),
        "--timestamp",
        timestamp,
        "--test",
        "a-numbers-b-static",
        "--test-b",
        "dot",
        "--numbers",
        "1,2,3,4,5",
        "--number-size-px",
        "100",
        "--b-dot-x",
        "960",
        "--b-dot-y",
        "540",
        "--b-dot-radius",
        "20",
        "--exposure-us",
        str(exposure),
        "--dark-time-us",
        "100",
        "--trigger-out-2-rising-delay-us",
        str(rising_delay_us),
        "--accumulation-start-offset-us",
        "-250",
        "--runtime-seconds",
        "1",
        "--polarity-mode",
        "ignore",
        "--event-noise-filter",
        "none",
        "--save-filtered-events",
        "--accumulation-cycles",
        "1",
        "-v",
    ]


def _argv_row(tmp_path, timestamp, exposure, rising_delay_us):
    return {"sync_check_argv": shlex.join(_sync_check_argv(tmp_path, timestamp, exposure, rising_delay_us))}


def _command_row(tmp_path, timestamp, exposure, rising_delay_us):
    return {
        "command":
        shlex.join(["./run_camera_sync_check.sh", *_sync_check_argv(tmp_path, timestamp, exposure, rising_delay_us)])
    }


def test_sync_sweep_dry_run_creates_one_run_per_manifest_row(tmp_path):
    manifest = tmp_path / "sweep.csv"
    _write_manifest(
        manifest,
        [
            _argv_row(tmp_path,
                      "sweep-000",
                      600,
                      0),
            _argv_row(tmp_path,
                      "sweep-001",
                      1000,
                      -20),
        ],
    )

    assert sync_sweep.main(["--dry-run", "--manifest", str(manifest)]) == 0

    first = json.loads(
        (tmp_path / "sweep-000-sync-check" / "metadata.json").read_text(encoding="utf-8"))
    second = json.loads(
        (tmp_path / "sweep-001-sync-check" / "metadata.json").read_text(encoding="utf-8"))
    assert first["dry_run"] is True
    assert first["exposure_us"] == 600
    assert first["accumulation_start_offset_us"] == -250
    assert first["accumulation_cycles"] == 1
    assert first["trigger_policy"]["rising_delay_us"] == 0
    assert first["trigger_policy"]["falling_delay_us"] == 20
    assert second["exposure_us"] == 1000
    assert second["accumulation_start_offset_us"] == -250
    assert second["accumulation_cycles"] == 1
    assert second["trigger_policy"]["rising_delay_us"] == -20
    assert second["trigger_policy"]["falling_delay_us"] == 0


def test_camera_sync_sweep_cli_dry_run_creates_artifacts(tmp_path):
    from dmdcontrol.cli.main import main

    manifest = tmp_path / "sweep.csv"
    _write_manifest(manifest, [_argv_row(tmp_path, "sweep-000", 600, 0)])

    assert main([
        "camera",
        "sync-sweep",
        "--dry-run",
        "--manifest",
        str(manifest),
    ]) == 0

    metadata = json.loads(
        (tmp_path / "sweep-000-sync-check" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["number_sequence"] == [1, 2, 3, 4, 5]
    assert metadata["exposure_us"] == 600


def test_sync_sweep_command_row_preserves_original_command_in_artifacts(tmp_path):
    manifest = tmp_path / "sweep.csv"
    _write_manifest(manifest, [_command_row(tmp_path, "sweep-000", 600, 0)])

    assert sync_sweep.main(["--dry-run", "--manifest", str(manifest)]) == 0

    run = tmp_path / "sweep-000-sync-check"
    metadata = json.loads((run / "metadata.json").read_text(encoding="utf-8"))
    command = (run / "command.txt").read_text(encoding="utf-8")

    assert metadata["command"][0] == "./run_camera_sync_check.sh"
    assert command.startswith("./run_camera_sync_check.sh ")


def test_sync_sweep_rejects_manifest_without_explicit_command(tmp_path):
    manifest = tmp_path / "sweep.csv"
    _write_manifest(
        manifest,
        [
            {
                "output_root": str(tmp_path),
                "timestamp": "sweep-000",
                "exposure_us": "600",
            }
        ],
    )

    with pytest.raises(SystemExit, match="sync_check_argv or command"):
        sync_sweep.main(["--dry-run", "--manifest", str(manifest)])


def test_sync_sweep_live_opens_camera_once_for_all_rows(tmp_path, monkeypatch):
    manifest = tmp_path / "sweep.csv"
    _write_manifest(
        manifest,
        [
            _argv_row(tmp_path,
                      "sweep-000",
                      600,
                      0),
            _argv_row(tmp_path,
                      "sweep-001",
                      1000,
                      -20),
        ],
    )
    calls = {
        "open": 0,
        "runs": [],
        "writers": [],
        "closed_writers": 0,
        "closed_captures": 0,
        "flushes": [],
    }
    capture = object()
    ready = SimpleNamespace(event_resolution=(346, 260))

    def fake_open_ready_camera_capture(args):
        calls["open"] += 1
        return capture, ready

    def fake_open_camera_writer(run, opened_capture):
        assert opened_capture is capture
        writer = object()
        calls["writers"].append((run.path.name, writer))
        return writer

    def fake_live_capture(args, run, opened_capture, writer, opened_ready, command_argv=None):
        assert opened_capture is capture
        assert opened_ready is ready
        calls["runs"].append((args.timestamp, run.path.name, writer, command_argv))
        return 0

    def fake_close_camera_resources(resources, *, shutdown_streams):
        if resources.get("writer") is not None:
            calls["closed_writers"] += 1
        if resources.get("capture") is not None:
            calls["closed_captures"] += 1

    def fake_flush_stale_batches(opened_capture, *, reads, include_triggers=True):
        assert opened_capture is capture
        calls["flushes"].append((reads, include_triggers))
        return {}

    monkeypatch.setattr(sync_sweep, "open_ready_camera_capture", fake_open_ready_camera_capture)
    monkeypatch.setattr(sync_sweep, "open_camera_writer", fake_open_camera_writer)
    monkeypatch.setattr(sync_sweep, "flush_stale_batches", fake_flush_stale_batches)
    monkeypatch.setattr(sync_sweep.sync_check, "live_capture", fake_live_capture)
    monkeypatch.setattr(sync_sweep, "close_camera_resources", fake_close_camera_resources)

    assert sync_sweep.main(["--manifest", str(manifest)]) == 0

    assert calls["open"] == 1
    assert [run[0] for run in calls["runs"]] == ["sweep-000", "sweep-001"]
    assert [writer[0] for writer in calls["writers"]] == [
        "sweep-000-sync-check",
        "sweep-001-sync-check",
    ]
    assert calls["closed_writers"] == 2
    assert calls["closed_captures"] == 1
    assert calls["flushes"] == [(32, True), (32, True)]
