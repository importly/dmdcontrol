import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dmdcontrol.camera.accumulation import TriggerRecord
from dmdcontrol.camera.reprocess_aedat4 import (
    Aedat4RecordingData,
    build_parser,
    _trigger_edge_name,
    _trigger_record,
    main,
)


def test_trigger_edge_name_maps_dv_trigger_enum_text():
    assert _trigger_edge_name("TriggerType.EXTERNAL_SIGNAL_RISING_EDGE") == "rising"
    assert _trigger_edge_name("TriggerType.EXTERNAL_SIGNAL_FALLING_EDGE") == "falling"


def test_trigger_record_converts_dv_trigger_object():
    trigger = SimpleNamespace(
        timestamp=lambda: 123,
        type=lambda: "TriggerType.EXTERNAL_SIGNAL_RISING_EDGE",
    )

    assert _trigger_record(trigger) == TriggerRecord(timestamp=123, edge="rising")


def test_reprocess_main_writes_derived_artifacts_from_reader(monkeypatch, tmp_path):
    run_dir = tmp_path / "source-sync-check"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps({
            "accumulation_window_us": 20,
            "polarity_mode": "positive",
            "expected_trigger_count": 2,
            "accumulation_cycles": 1,
        }),
        encoding="utf-8",
    )
    raw_path = run_dir / "raw.aedat4"
    raw_path.write_bytes(b"fake")

    events = np.array(
        [
            (105, 1, 1, True),
            (125, 2, 1, True),
        ],
        dtype=[("timestamp", np.int64), ("x", np.int16), ("y", np.int16), ("polarity", np.bool_)],
    )

    def fake_read(path):
        assert Path(path) == raw_path
        return Aedat4RecordingData(
            events=[events],
            triggers=[
                TriggerRecord(timestamp=100, edge="rising"),
                TriggerRecord(timestamp=120, edge="rising"),
            ],
            resolution=(4, 3),
            stats={"event_count": 2, "trigger_count": 2},
        )

    monkeypatch.setattr("dmdcontrol.camera.reprocess_aedat4.read_aedat4_recording", fake_read)
    output_dir = tmp_path / "derived"

    assert main([
        str(run_dir),
        "--output-dir",
        str(output_dir),
        "--accumulation-start-offset-us",
        "5",
    ]) == 0

    accumulated = np.load(output_dir / "accumulated.npy")
    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))

    assert accumulated.shape == (2, 3, 4)
    assert accumulated[0, 1, 1] == 1
    assert accumulated[1, 1, 2] == 1
    assert summary["window_start_offset_us"] == 5
    assert metadata["mode"] == "aedat4-reprocess"
    assert metadata["source_aedat4"] == str(raw_path)


@pytest.mark.parametrize("flag", ["--trigger-cluster-us", "--cycle-selection"])
def test_reprocess_parser_rejects_removed_trigger_selection_options(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["source-run", flag, "1"])
