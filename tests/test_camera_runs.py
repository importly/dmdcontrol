import importlib
import json

import numpy as np
from PIL import Image

from dmdcontrol.camera.accumulation import EventRecord, TriggerRecord
from dmdcontrol.camera.local_support_filter import LocalSupportFilterConfig
from dmdcontrol.camera.runs import (
    create_run_directory,
    write_capture_artifacts,
    write_run_metadata,
)


def test_camera_runs_is_package_with_focused_modules():
    modules = {
        importlib.import_module("dmdcontrol.camera.runs.directory"),
        importlib.import_module("dmdcontrol.camera.runs.capture_artifacts"),
        importlib.import_module("dmdcontrol.camera.runs.accumulation_artifacts"),
        importlib.import_module("dmdcontrol.camera.runs.image_artifacts"),
    }

    assert {module.__name__.rsplit(".", 1)[-1] for module in modules} == {
        "directory",
        "capture_artifacts",
        "accumulation_artifacts",
        "image_artifacts",
    }


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
        EventRecord(timestamp=105,
                    x=2,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=110,
                    x=2,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=210,
                    x=0,
                    y=0,
                    polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=100,
                      edge="rising"),
        TriggerRecord(timestamp=200,
                      edge="falling"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(4,
                    3),
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
    with Image.open(run.path / "accumulated_001.png") as image:
        assert image.mode == "L"
        assert image.size == (4, 3)
    with Image.open(run.contact_sheet_path) as image:
        assert image.mode == "L"
        assert image.size == (4, 3)
    assert summary_json == summary
    assert summary["actual_trigger_count"] == 1
    assert summary["accumulated_shape"] == [1, 3, 4]
    assert summary["event_time_range_us"] == [105, 210]
    assert summary["accumulation_event_time_range_us"] == [105, 210]
    assert summary["rising_trigger_time_range_us"] == [100, 100]
    assert summary["events_per_accumulation_window"] == [2]
    assert summary["events_per_pre_trigger_window"] == [0]
    assert summary["events_per_post_window"] == [0]
    assert summary["accumulated_nonzero_pixels"] == [1]
    assert summary["accumulated_abs_sums"] == [2.0]


def test_write_capture_artifacts_keeps_signed_png_background_black(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260604-120113",
    )
    events = [
        EventRecord(timestamp=101,
                    x=0,
                    y=0,
                    polarity=True),
        EventRecord(timestamp=102,
                    x=1,
                    y=0,
                    polarity=False),
    ]
    triggers = [TriggerRecord(timestamp=100, edge="rising")]

    write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(3,
                    2),
        window_us=10,
        polarity_mode="signed",
    )

    accumulated = np.load(run.accumulated_path)
    with Image.open(run.path / "accumulated_001.png") as image:
        pixels = np.array(image)

    assert accumulated[0, 0, 0] == 1
    assert accumulated[0, 0, 1] == -1
    assert accumulated[0, 1, 2] == 0
    assert pixels[0, 0] == 255
    assert pixels[0, 1] == 255
    assert pixels[1, 2] == 0


def test_write_capture_artifacts_applies_window_start_offset(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260604-120115",
    )
    events = [
        EventRecord(timestamp=105,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=125,
                    x=2,
                    y=1,
                    polarity=True),
    ]
    triggers = [TriggerRecord(timestamp=100, edge="rising")]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(4,
                    3),
        window_us=20,
        polarity_mode="positive",
        window_start_offset_us=20,
    )

    accumulated = np.load(run.accumulated_path)
    assert accumulated[0, 1, 1] == 0
    assert accumulated[0, 1, 2] == 1
    assert summary["window_start_offset_us"] == 20
    assert summary["events_per_accumulation_window"] == [1]
    assert summary["events_per_pre_trigger_window"] == [1]


def test_write_capture_artifacts_can_use_cycle_columns_for_contact_sheet(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260604-120116",
    )
    triggers = [TriggerRecord(timestamp=100 + index * 10, edge="rising") for index in range(6)]

    write_capture_artifacts(
        run,
        events=[],
        triggers=triggers,
        resolution=(4,
                    3),
        window_us=5,
        polarity_mode="positive",
        contact_sheet_columns=3,
    )

    with Image.open(run.contact_sheet_path) as image:
        assert image.size == (12, 6)


def test_write_capture_artifacts_uses_log_grayscale_for_weak_events(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260604-120114",
    )
    events = [EventRecord(timestamp=101, x=0, y=0, polarity=True)]
    events.extend(
        EventRecord(timestamp=101 + offset,
                    x=1,
                    y=0,
                    polarity=True) for offset in range(100))
    triggers = [TriggerRecord(timestamp=100, edge="rising")]

    write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(3,
                    2),
        window_us=200,
        polarity_mode="positive",
    )

    accumulated = np.load(run.accumulated_path)
    with Image.open(run.path / "accumulated_001.png") as image:
        pixels = np.array(image)

    assert accumulated[0, 0, 0] == 1
    assert accumulated[0, 0, 1] == 100
    assert accumulated[0, 1, 2] == 0
    assert pixels[0, 0] > 20
    assert pixels[0, 0] < pixels[0, 1]
    assert pixels[0, 1] == 255
    assert pixels[1, 2] == 0


def test_write_capture_artifacts_filters_events_before_accumulation(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260527-120107",
    )
    events = [
        EventRecord(timestamp=101,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=102,
                    x=1,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=103,
                    x=2,
                    y=2,
                    polarity=False),
    ]
    triggers = [
        TriggerRecord(timestamp=100,
                      edge="rising"),
        TriggerRecord(timestamp=150,
                      edge="falling"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(4,
                    4),
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
        EventRecord(timestamp=101,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=201,
                    x=2,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=301,
                    x=3,
                    y=3,
                    polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=100,
                      edge="rising"),
        TriggerRecord(timestamp=200,
                      edge="rising"),
        TriggerRecord(timestamp=300,
                      edge="rising"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
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


def test_write_capture_artifacts_aligns_accumulation_triggers_to_event_range(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260602-120109",
    )
    events = [
        EventRecord(timestamp=1000,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1010,
                    x=2,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=1110,
                    x=3,
                    y=3,
                    polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=100,
                      edge="rising"),
        TriggerRecord(timestamp=200,
                      edge="rising"),
        TriggerRecord(timestamp=1000,
                      edge="rising"),
        TriggerRecord(timestamp=1100,
                      edge="rising"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
        window_us=50,
        polarity_mode="positive",
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)

    assert trigger_lines == [
        "index,timestamp,edge",
        "0,1000,rising",
        "1,1100,rising",
    ]
    assert accumulated.shape == (2, 5, 5)
    assert accumulated[0, 1, 1] == 1
    assert accumulated[0, 2, 2] == 1
    assert accumulated[1, 3, 3] == 1
    assert summary["raw_rising_trigger_count"] == 4
    assert summary["actual_trigger_count"] == 2
    assert summary["raw_rising_trigger_time_range_us"] == [100, 1100]
    assert summary["rising_trigger_time_range_us"] == [1000, 1100]
    assert summary["trigger_alignment"]["mode"] == "event_overlap"
    assert summary["trigger_alignment"]["dropped_before_event_count"] == 2
    assert summary["trigger_alignment"]["dropped_after_event_count"] == 0


def test_write_capture_artifacts_keeps_close_triggers_as_separate_frames(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260603-120110",
    )
    events = [
        EventRecord(timestamp=1001,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1009,
                    x=2,
                    y=2,
                    polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=1000,
                      edge="rising"),
        TriggerRecord(timestamp=1008,
                      edge="rising"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
        window_us=5,
        polarity_mode="positive",
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)

    assert trigger_lines == [
        "index,timestamp,edge",
        "0,1000,rising",
        "1,1008,rising",
    ]
    assert accumulated.shape == (2, 5, 5)
    assert accumulated[0, 1, 1] == 1
    assert accumulated[1, 2, 2] == 1
    assert summary["raw_rising_trigger_count"] == 2
    assert summary["aligned_rising_trigger_count"] == 2
    assert summary["selected_rising_trigger_count"] == 2
    assert "trigger_clustering" not in summary
    assert "clustered_rising_trigger_count" not in summary


def test_write_capture_artifacts_selects_first_full_trigger_cycle(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260603-120111",
    )
    events = [
        EventRecord(timestamp=1001,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1101,
                    x=2,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=1201,
                    x=3,
                    y=3,
                    polarity=True),
        EventRecord(timestamp=1301,
                    x=4,
                    y=4,
                    polarity=True),
        EventRecord(timestamp=1401,
                    x=0,
                    y=0,
                    polarity=True),
        EventRecord(timestamp=1501,
                    x=1,
                    y=0,
                    polarity=True),
    ]
    triggers = [
        TriggerRecord(timestamp=1000,
                      edge="rising"),
        TriggerRecord(timestamp=1100,
                      edge="rising"),
        TriggerRecord(timestamp=1200,
                      edge="rising"),
        TriggerRecord(timestamp=1300,
                      edge="rising"),
        TriggerRecord(timestamp=1400,
                      edge="rising"),
        TriggerRecord(timestamp=1500,
                      edge="rising"),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
        window_us=20,
        polarity_mode="positive",
        trigger_cycle_length=3,
        accumulation_cycles=1,
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)

    assert trigger_lines == [
        "index,timestamp,edge",
        "0,1000,rising",
        "1,1100,rising",
        "2,1200,rising",
    ]
    assert accumulated.shape == (3, 5, 5)
    assert summary["actual_trigger_count"] == 3
    assert summary["selected_rising_trigger_count"] == 3
    assert summary["trigger_cycle_limit"] == {
        "cycle_length": 3,
        "requested_cycles": 1,
        "available_full_cycles": 2,
        "selected_cycle_indices": [0],
        "selected_trigger_count": 3,
    }
    assert summary["frame_artifacts"] == [
        "accumulated_001.png",
        "accumulated_002.png",
        "accumulated_003.png",
    ]
    assert not (run.path / "accumulated_004.png").exists()


def test_write_capture_artifacts_skips_startup_leader_before_cycle_selection(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260603-120112",
    )
    triggers = [
        TriggerRecord(timestamp=1000 + index * 100,
                      edge="rising") for index in range(6)
    ]
    events = [
        EventRecord(timestamp=1001,
                    x=0,
                    y=0,
                    polarity=True),
        EventRecord(timestamp=1101,
                    x=0,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1201,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1301,
                    x=2,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=1401,
                    x=3,
                    y=3,
                    polarity=True),
        EventRecord(timestamp=1501,
                    x=4,
                    y=4,
                    polarity=True),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
        window_us=20,
        polarity_mode="positive",
        trigger_cycle_length=2,
        accumulation_cycles=1,
        startup_leader_trigger_count=2,
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)

    assert trigger_lines == [
        "index,timestamp,edge",
        "0,1200,rising",
        "1,1300,rising",
    ]
    assert accumulated.shape == (2, 5, 5)
    assert summary["startup_leader_skip"] == {
        "requested_trigger_count": 2,
        "skipped_trigger_count": 2,
        "input_trigger_count": 6,
        "remaining_trigger_count": 4,
    }
    assert summary["trigger_cycle_limit"]["selected_cycle_indices"] == [0]


def test_write_capture_artifacts_skips_startup_leader_before_event_alignment(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260603-120113",
    )
    triggers = [
        TriggerRecord(timestamp=1000 + index * 100,
                      edge="rising") for index in range(4)
    ]
    events = [
        EventRecord(timestamp=1201,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1301,
                    x=2,
                    y=2,
                    polarity=True),
    ]

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
        window_us=20,
        polarity_mode="positive",
        trigger_cycle_length=2,
        accumulation_cycles=1,
        startup_leader_trigger_count=2,
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()
    accumulated = np.load(run.accumulated_path)

    assert trigger_lines == [
        "index,timestamp,edge",
        "0,1200,rising",
        "1,1300,rising",
    ]
    assert accumulated.shape == (2, 5, 5)
    assert summary["startup_leader_skip"] == {
        "requested_trigger_count": 2,
        "skipped_trigger_count": 2,
        "input_trigger_count": 4,
        "remaining_trigger_count": 2,
    }
    assert summary["trigger_alignment"]["input_trigger_count"] == 2
    assert summary["trigger_alignment"]["aligned_trigger_count"] == 2


def test_write_capture_artifacts_selects_first_cycle_block(tmp_path):
    run = create_run_directory(
        "sync-check",
        output_root=tmp_path,
        timestamp="20260604-120114",
    )
    triggers = [TriggerRecord(timestamp=1000 + index * 100, edge="rising") for index in range(15)]
    events = []
    cycle_counts = [90, 3, 60, 60, 60]
    for cycle_index, cycle_total in enumerate(cycle_counts):
        event_count_per_trigger = cycle_total // 3
        for slot in range(3):
            trigger_index = cycle_index * 3 + slot
            for offset in range(event_count_per_trigger):
                events.append(
                    EventRecord(
                        timestamp=1000 + trigger_index * 100 + offset,
                        x=offset % 5,
                        y=cycle_index,
                        polarity=True,
                    ))

    summary = write_capture_artifacts(
        run,
        events=events,
        triggers=triggers,
        resolution=(5,
                    5),
        window_us=90,
        polarity_mode="positive",
        trigger_cycle_length=3,
        accumulation_cycles=3,
    )

    trigger_lines = run.triggers_path.read_text(encoding="utf-8").splitlines()

    assert summary["trigger_cycle_limit"]["selected_cycle_indices"] == [0, 1, 2]
    assert trigger_lines[1] == "0,1000,rising"
    assert trigger_lines[-1] == "8,1800,rising"
