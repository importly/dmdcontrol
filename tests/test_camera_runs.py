import json

import numpy as np

from dmdcontrol.camera.accumulation import EventRecord, TriggerRecord
from dmdcontrol.camera.local_support_filter import LocalSupportFilterConfig
from dmdcontrol.camera.runs import (
    create_run_directory,
    write_capture_artifacts,
    write_run_metadata,
)


def test_create_run_directory_uses_mode_and_timestamp(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260527-120102",
    )

    assert run.path == tmp_path / "20260527-120102-sync-check"
    assert run.path.is_dir()
    assert run.raw_recording_path.name == "raw.aedat4"
    assert run.metadata_path.name == "metadata.json"


def test_write_run_metadata_lists_artifacts(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260527-120102",
    )
    payload = write_run_metadata(run, {"mode": "sync-check"}, artifacts=["raw.aedat4"])

    saved = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert saved["mode"] == "sync-check"
    assert saved["artifacts"] == ["raw.aedat4"]
    assert saved["run_directory"] == str(run.path)
    assert payload["metadata_path"].endswith("metadata.json")


def test_write_capture_artifacts_saves_rising_trigger_accumulations(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260527-120106",
    )
    events = [
        EventRecord(timestamp=105, x=2, y=1, polarity=True),
        EventRecord(timestamp=110, x=2, y=1, polarity=True),
        EventRecord(timestamp=210, x=0, y=0, polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=100, edge="rising"),
        TriggerRecord(timestamp=200, edge="falling"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(4, 3),
        window_us=50,
        polarity_mode="positive",
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)
    summary_json = json.loads(run.summary_path.read_text(encoding="utf-8"))

    assert trigger_lines == ["index,timestamp,edge", "0,100,rising"]
    assert accumulated.shape == (1, 3, 4)
    assert accumulated[0, 1, 2] == 2
    assert (run.path / "accumulated_001.png").exists()
    assert run.contact_sheet_path.exists()
    assert summary_json == summary
    assert summary["actual_trigger_count"] == 1
    assert summary["accumulated_shape"] == [1, 3, 4]


def test_write_capture_artifacts_filters_events_before_accumulation(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260527-120107",
    )
    events = [
        EventRecord(timestamp=101, x=1, y=1, polarity=True),
        EventRecord(timestamp=102, x=1, y=2, polarity=True),
        EventRecord(timestamp=103, x=2, y=2, polarity=False),
    ]
    triggers = [
        TriggerRecord(timestamp=100, edge="rising"),
        TriggerRecord(timestamp=150, edge="falling"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(4, 4),
        window_us=10,
        polarity_mode="ignore",
        event_noise_filter=LocalSupportFilterConfig(
            enabled=True,
            delta_t_us=50,
            window_px=3,
            threshold=1,
            polarity="same",
        ),
        save_filtered_events=True,
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)
    filtered_events = np.load(run.path / "filtered_events.npz")

    assert trigger_lines == ["index,timestamp,edge", "0,100,rising"]
    assert accumulated.shape == (1, 4, 4)
    assert np.sum(accumulated) == 1.0
    assert accumulated[0, 2, 1] == 1.0
    assert (run.path / "filtered_accumulated_001.png").exists()
    assert (run.path / "filtered_contact_sheet.png").exists()
    assert filtered_events["x"].tolist() == [1]
    assert filtered_events["y"].tolist() == [2]
    assert filtered_events["t"].tolist() == [102]
    assert filtered_events["p"].tolist() == [True]
    assert summary["accumulation_event_source"] == "filtered"
    assert summary["filtered_frame_artifacts"] == ["filtered_accumulated_001.png"]
    assert summary["filtered_contact_sheet_artifact"] == "filtered_contact_sheet.png"
    assert summary["filtered_events_artifact"] == "filtered_events.npz"
    assert summary["event_noise_filter"]["raw_events"] == 3
    assert summary["event_noise_filter"]["filtered_events"] == 1
    assert summary["event_noise_filter"]["filtered_on"] == 1
    assert summary["event_noise_filter"]["filtered_off"] == 0


def test_write_capture_artifacts_can_limit_accumulation_triggers(tmp_path):
    run = create_run_directory(
        "pair-capture",
        output_root=tmp_path,
        timestamp="20260527-120108",
    )
    events = [
        EventRecord(timestamp=101, x=1, y=1, polarity=True),
        EventRecord(timestamp=201, x=2, y=2, polarity=True),
        EventRecord(timestamp=301, x=3, y=3, polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=100, edge="rising"),
        TriggerRecord(timestamp=200, edge="rising"),
        TriggerRecord(timestamp=300, edge="rising"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5, 5),
        window_us=10,
        polarity_mode="positive",
        max_accumulation_triggers=2,
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)

    assert trigger_lines == [
        "index,timestamp,edge",
        "0,100,rising",
        "1,200,rising",
    ]
    assert accumulated.shape == (2, 5, 5)
    assert accumulated[0, 1, 1] == 1
    assert accumulated[1, 2, 2] == 1
    assert summary["actual_trigger_count"] == 2
    assert summary["raw_rising_trigger_count"] == 3
    assert summary["max_accumulation_triggers"] == 2
    assert summary["accumulation_trigger_limited"] is True
