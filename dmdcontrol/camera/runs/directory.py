from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast


@dataclass(frozen=True)
class CameraRunDirectory:
    path: Path
    raw_recording_path: Path
    metadata_path: Path
    command_path: Path
    log_path: Path
    triggers_path: Path
    accumulated_path: Path
    timing_path: Path
    contact_sheet_path: Path
    summary_path: Path

def final_capture_artifacts(artifact_summary):
    artifacts = [
        "raw.aedat4",
        "metadata.json",
        "command.txt",
        "run.log",
        "timing.json",
    ]
    if artifact_summary is None:
        return artifacts

    artifacts.extend([
        "triggers.csv",
        "accumulated.npy",
        "contact_sheet.png",
        "summary.json",
    ])
    artifacts.extend(artifact_summary.get("frame_artifacts", []))
    artifacts.extend(artifact_summary.get("filtered_frame_artifacts", []))
    if artifact_summary.get("filtered_contact_sheet_artifact"):
        artifacts.append(artifact_summary["filtered_contact_sheet_artifact"])
    if artifact_summary.get("filtered_events_artifact"):
        artifacts.append(artifact_summary["filtered_events_artifact"])
    return artifacts

def default_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")

def create_run_directory(mode, output_root=None, timestamp=None):
    root = Path(output_root) if output_root is not None else Path("runs") / "camera"
    run_path = root / f"{timestamp or default_timestamp()}-{mode}"
    run_path.mkdir(parents=True, exist_ok=False)
    return CameraRunDirectory(
        path=run_path,
        raw_recording_path=run_path / "raw.aedat4",
        metadata_path=run_path / "metadata.json",
        command_path=run_path / "command.txt",
        log_path=run_path / "run.log",
        triggers_path=run_path / "triggers.csv",
        accumulated_path=run_path / "accumulated.npy",
        timing_path=run_path / "timing.json",
        contact_sheet_path=run_path / "contact_sheet.png",
        summary_path=run_path / "summary.json",
    )

def write_json(path, payload):
    output_path = Path(path)
    output_path.write_text(
        json.dumps(payload,
                   indent=2,
                   sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload

def metadata_dict(value):
    if not isinstance(value, type) and is_dataclass(value):
        return asdict(cast(Any, value))
    return dict(getattr(value, "__dict__", {}))

def write_run_metadata(run_directory, metadata, artifacts=None):
    payload = dict(metadata)
    payload["run_directory"] = str(run_directory.path)
    payload["metadata_path"] = str(run_directory.metadata_path)
    payload["artifacts"] = list(artifacts or [])
    write_json(run_directory.metadata_path, payload)
    return payload
