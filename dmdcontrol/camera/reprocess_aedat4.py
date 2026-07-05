from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dmdcontrol.camera.accumulation import TriggerRecord
from dmdcontrol.camera.capture import merge_time_range
from dmdcontrol.camera.runs import (
    CameraRunDirectory,
    write_capture_artifacts,
    write_run_metadata,
)
from dmdcontrol.support.argparse_types import nonnegative_int, positive_int


@dataclass(frozen=True)
class Aedat4RecordingData:
    events: list[np.ndarray]
    triggers: list[TriggerRecord]
    resolution: tuple[int, int]
    stats: dict[str, object]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dmdcontrol camera reprocess-aedat4",
        description="Regenerate accumulation artifacts from an existing raw.aedat4 recording.",
    )
    parser.add_argument("run_dir", help="Run directory containing raw.aedat4 and metadata.json.")
    parser.add_argument("--aedat4", default=None, help="Override the AEDAT4 file path.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help=
        "Directory for derived artifacts. Defaults to RUN_DIR/analysis_outputs/reprocessed_aedat4.",
    )
    parser.add_argument("--window-us", type=nonnegative_int, default=None)
    parser.add_argument("--accumulation-start-offset-us", type=int, default=0)
    parser.add_argument("--polarity-mode", choices=("positive", "signed", "ignore"), default=None)
    parser.add_argument("--trigger-cycle-length", type=positive_int, default=None)
    parser.add_argument("--accumulation-cycles", type=positive_int, default=None)
    parser.add_argument("--max-accumulation-triggers", type=positive_int, default=None)
    parser.add_argument("--contact-sheet-columns", type=positive_int, default=None)
    parser.add_argument("--startup-leader-trigger-count", type=nonnegative_int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_dir = Path(args.run_dir).expanduser()
    if not run_dir.is_absolute():
        run_dir = Path.cwd() / run_dir
    metadata_path = run_dir / "metadata.json"
    source_metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    options = _resolve_options(args, source_metadata)
    aedat4_path = (Path(args.aedat4).expanduser() if args.aedat4 else run_dir / "raw.aedat4")
    if not aedat4_path.is_absolute():
        aedat4_path = Path.cwd() / aedat4_path
    output_dir = (
        Path(args.output_dir).expanduser() if args.output_dir else run_dir / "analysis_outputs" /
        "reprocessed_aedat4")
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    recording = read_aedat4_recording(aedat4_path)
    derived_run = CameraRunDirectory(
        path=output_dir,
        raw_recording_path=aedat4_path,
        metadata_path=output_dir / "metadata.json",
        command_path=output_dir / "command.txt",
        log_path=output_dir / "run.log",
        triggers_path=output_dir / "triggers.csv",
        accumulated_path=output_dir / "accumulated.npy",
        timing_path=output_dir / "timing.json",
        contact_sheet_path=output_dir / "contact_sheet.png",
        summary_path=output_dir / "summary.json",
    )
    derived_run.command_path.write_text(" ".join(sys.argv) + "\n", encoding="utf-8")
    derived_run.log_path.write_text("aedat4 reprocess\n", encoding="utf-8")

    summary = write_capture_artifacts(
        derived_run,
        events=recording.events,
        triggers=recording.triggers,
        resolution=recording.resolution,
        window_us=options["window_us"],
        polarity_mode=options["polarity_mode"],
        window_start_offset_us=options["accumulation_start_offset_us"],
        max_accumulation_triggers=options["max_accumulation_triggers"],
        trigger_cycle_length=options["trigger_cycle_length"],
        accumulation_cycles=options["accumulation_cycles"],
        contact_sheet_columns=options["contact_sheet_columns"],
        startup_leader_trigger_count=options["startup_leader_trigger_count"],
    )
    metadata = {
        "mode": "aedat4-reprocess",
        "source_run_directory": str(run_dir),
        "source_aedat4": str(aedat4_path),
        "source_metadata_path": str(metadata_path),
        "options": options,
        "aedat4": recording.stats,
    }
    artifacts = [
        "metadata.json",
        "command.txt",
        "run.log",
        "triggers.csv",
        "accumulated.npy",
        "contact_sheet.png",
        "summary.json",
        *summary.get("frame_artifacts",
                     []),
    ]
    write_run_metadata(derived_run, metadata, artifacts=artifacts)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "actual_trigger_count": summary["actual_trigger_count"],
                "raw_rising_trigger_count": summary["raw_rising_trigger_count"],
                "window_us": summary["window_us"],
                "window_start_offset_us": summary["window_start_offset_us"],
            },
            indent=2,
            sort_keys=True,
        ))
    return 0


def read_aedat4_recording(path: str | Path) -> Aedat4RecordingData:
    import dv_processing as dv

    recording_path = Path(path)
    if not recording_path.exists():
        raise FileNotFoundError(recording_path)
    recording = dv.io.MonoCameraRecording(str(recording_path))
    if not recording.isEventStreamAvailable():
        raise RuntimeError(f"{recording_path} has no event stream")
    if not recording.isTriggerStreamAvailable():
        raise RuntimeError(f"{recording_path} has no trigger stream")

    events, event_stats = _read_event_batches(recording)
    recording.resetSequentialRead()
    triggers, trigger_stats = _read_trigger_batches(recording)
    resolution = tuple(int(value) for value in recording.getEventResolution())
    stats = {
        "event_batches": event_stats["batches"],
        "event_count": event_stats["count"],
        "event_time_range_us": event_stats["time_range_us"],
        "trigger_batches": trigger_stats["batches"],
        "trigger_count": trigger_stats["count"],
        "trigger_time_range_us": trigger_stats["time_range_us"],
        "trigger_edges": trigger_stats["edges"],
        "resolution": list(resolution),
    }
    return Aedat4RecordingData(
        events=events,
        triggers=triggers,
        resolution=resolution,
        stats=stats,
    )


def _read_event_batches(recording) -> tuple[list[np.ndarray], dict[str, object]]:
    batches = []
    count = 0
    time_range = None
    while True:
        batch = recording.getNextEventBatch()
        if batch is None:
            break
        if len(batch) == 0:
            continue
        array = np.asarray(batch.numpy()).copy()
        batches.append(array)
        count += len(array)
        time_range = merge_time_range(time_range, _array_time_range(array))
    return batches, {
        "batches": len(batches),
        "count": count,
        "time_range_us": _json_time_range(time_range), }


def _read_trigger_batches(recording) -> tuple[list[TriggerRecord], dict[str, object]]:
    triggers = []
    batch_count = 0
    time_range = None
    edge_counts = {}
    while True:
        batch = recording.getNextTriggerBatch()
        if batch is None:
            break
        if len(batch) == 0:
            continue
        batch_count += 1
        for trigger in batch:
            record = _trigger_record(trigger)
            triggers.append(record)
            edge_counts[record.edge] = edge_counts.get(record.edge, 0) + 1
            time_range = merge_time_range(time_range, (record.timestamp, record.timestamp))
    return triggers, {
        "batches": batch_count,
        "count": len(triggers),
        "time_range_us": _json_time_range(time_range),
        "edges": edge_counts, }


def _trigger_record(trigger) -> TriggerRecord:
    timestamp = int(_record_value(trigger, "timestamp"))
    trigger_type = _record_value(trigger, "type", default=None)
    return TriggerRecord(timestamp=timestamp, edge=_trigger_edge_name(trigger_type))


def _trigger_edge_name(trigger_type) -> str:
    value = str(trigger_type).lower()
    if "rising" in value:
        return "rising"
    if "falling" in value:
        return "falling"
    return value or "unknown"


def _record_value(record, name, default=None):
    if hasattr(record, name):
        value = getattr(record, name)
        return value() if callable(value) else value
    if isinstance(record, dict) and name in record:
        return record[name]
    if default is not None:
        return default
    raise AttributeError(f"{record!r} has no {name!r} field")


def _array_time_range(array) -> tuple[int, int] | None:
    field_names = array.dtype.names or ()
    timestamp_field = (
        "timestamp" if "timestamp" in field_names else "t" if "t" in field_names else None)
    if timestamp_field is None or len(array) == 0:
        return None
    timestamps = array[timestamp_field]
    return int(np.min(timestamps)), int(np.max(timestamps))


def _json_time_range(time_range):
    if time_range is None:
        return None
    return [int(time_range[0]), int(time_range[1])]


def _resolve_options(args, metadata: dict[str, object]) -> dict[str, object]:
    trigger_cycle_length = _first_not_none(
        args.trigger_cycle_length,
        metadata.get("expected_trigger_count"),
        len(metadata.get("number_sequence",
                         [])) or None,
    )
    return {
        "window_us":
        int(
            _first_not_none(
                args.window_us,
                metadata.get("accumulation_window_us"),
                metadata.get("exposure_us"),
                metadata.get("numbers_exposure_us"),
                metadata.get("count_exposure_us"),
                0,
            )),
        "accumulation_start_offset_us":
        int(args.accumulation_start_offset_us),
        "polarity_mode":
        str(_first_not_none(args.polarity_mode,
                            metadata.get("polarity_mode"),
                            "positive")),
        "trigger_cycle_length":
        int(trigger_cycle_length) if trigger_cycle_length is not None else None,
        "accumulation_cycles": (
            int(args.accumulation_cycles)
            if args.accumulation_cycles is not None else
            int(metadata["accumulation_cycles"]) if metadata.get("accumulation_cycles") is not None else None),
        "max_accumulation_triggers": (
            int(args.max_accumulation_triggers)
            if args.max_accumulation_triggers is not None else None),
        "contact_sheet_columns":
        int(_first_not_none(
            args.contact_sheet_columns,
            trigger_cycle_length,
            1,
        )),
        "startup_leader_trigger_count":
        int(
            _first_not_none(
                args.startup_leader_trigger_count,
                (metadata.get("startup_leader") or {}).get("trigger_count"),
                0,
            )),
    }


def _first_not_none(*values):
    for value in values:
        if value is not None:
            return value
    return None


if __name__ == "__main__":
    raise SystemExit(main())
