from __future__ import annotations

import argparse
import math
import sys
from dataclasses import asdict, is_dataclass
from importlib import import_module

from dmdcontrol.camera.capture import (
    AsyncCapture,
    append_batch_records,
    flush_stale_batches,
    record_until_trigger_count,
    validate_camera_ready,
)
from dmdcontrol.camera.discovery import (
    configure_camera_performance,
    configure_rising_edge_triggers,
    import_dv_processing,
)
from dmdcontrol.camera.local_support_filter import (
    add_event_noise_filter_arguments,
    event_noise_filter_config_from_args,
    event_noise_filter_metadata,
)
from dmdcontrol.camera.runs import (
    create_run_directory,
    write_capture_artifacts,
    write_json,
    write_run_metadata,
)


def parse_numbers(value: str) -> list[int]:
    try:
        numbers = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("numbers must be decimal digits") from exc
    if not numbers:
        raise argparse.ArgumentTypeError("numbers must not be empty")
    if any(number < 1 or number > 9 for number in numbers):
        raise argparse.ArgumentTypeError("numbers must be in the range 1..9")
    if len(numbers) > 24:
        raise argparse.ArgumentTypeError("numbers can contain at most 24 entries")
    return numbers


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be positive") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dmdcontrol camera sync-check",
        description="Paired DMD + DVXplorer sync check.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--timestamp", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--number-size-px", type=positive_int, default=420)
    parser.add_argument("--numbers", type=parse_numbers, default=parse_numbers("1,2,3,4,5"))
    parser.add_argument(
        "--numbers-exposure-us",
        type=positive_int,
        default=None,
        help="Optional per-bitplane LUT exposure override in microseconds. "
             "Omit for the maximum safe exposure at the configured VSYNC.",
    )
    parser.add_argument("--trigger-out-2-delay-fraction", type=float, default=0.03)
    parser.add_argument("--runtime-seconds", type=int, default=0)
    parser.add_argument(
        "--seq-utilization",
        type=float,
        default=None,
        help="Optional paired-runtime LUT budget utilization override. "
             "Use 1.0 only when intentionally using nearly the full VSYNC budget.",
    )
    parser.add_argument("--dmd-config", default=None)
    parser.add_argument("--hz", type=int, default=None)
    parser.add_argument("--test", default="numbers")
    parser.add_argument("--test-b", default="dot")
    parser.add_argument("--b-dot-x", type=int, default=960)
    parser.add_argument("--b-dot-y", type=int, default=540)
    parser.add_argument("--b-dot-radius", type=positive_int, default=40)
    parser.add_argument("--bias-sensitivity", default="default", choices=["default", "verylow", "low", "high", "veryhigh"])
    parser.add_argument("--efps", default="default", choices=["default", "variable", "variable_5000", "constant_1000", "constant_100"])
    parser.add_argument("--polarity-mode", default="positive", choices=["positive", "signed", "ignore"])
    parser.add_argument("--dark-time-us", type=int, default=None)
    add_event_noise_filter_arguments(parser)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def expected_trigger_count(args: argparse.Namespace) -> int:
    return len(args.numbers)


def dry_run(args: argparse.Namespace):
    run = create_run_directory("sync-check", args.output_root, timestamp=args.timestamp)
    event_filter = event_noise_filter_config_from_args(args)
    trigger_policy = {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "delay_fraction": args.trigger_out_2_delay_fraction,
    }
    metadata = {
        "mode": "sync-check",
        "dry_run": True,
        "command": sys.argv,
        "number_sequence": list(args.numbers),
        "number_size_px": args.number_size_px,
        "numbers_exposure_us": args.numbers_exposure_us,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "expected_trigger_count": expected_trigger_count(args),
        "trigger_mode": "per_bitplane",
        "bitplane_count": len(args.numbers),
        "seq_utilization": args.seq_utilization,
        "trigger_policy": trigger_policy,
        "bias_sensitivity": args.bias_sensitivity,
        "efps": args.efps,
        "polarity_mode": args.polarity_mode,
        "dark_time_us": args.dark_time_us,
        "event_noise_filter": event_noise_filter_metadata(event_filter),
        "save_filtered_events": args.save_filtered_events,
    }
    write_json(run.timing_path, trigger_policy)
    write_run_metadata(
        run,
        metadata,
        artifacts=["metadata.json", "timing.json", "command.txt", "run.log"],
    )
    run.command_path.write_text(
        "python -m dmdcontrol camera sync-check --dry-run\n",
        encoding="utf-8",
    )
    run.log_path.write_text("dry-run\n", encoding="utf-8")
    return run


def _asdict(value):
    if is_dataclass(value):
        return asdict(value)
    return dict(getattr(value, "__dict__", {}))


def _open_ready_camera(run, args):
    dv = import_dv_processing()
    capture = dv.io.camera.open()
    try:
        configure_camera_performance(capture, bias_sensitivity=args.bias_sensitivity, efps=args.efps)
        configure_rising_edge_triggers(capture)
        ready = validate_camera_ready(capture)
        flush_stale_batches(capture)
        writer = dv.io.MonoCameraWriter(str(run.raw_recording_path), capture)
    except Exception:
        del capture
        raise
    return capture, writer, ready


def _pair_runtime_seconds(args: argparse.Namespace) -> int:
    runtime_seconds = args.runtime_seconds
    if runtime_seconds <= 0:
        if args.numbers_exposure_us is None:
            runtime_seconds = 1
        else:
            sequence_seconds = len(args.numbers) * args.numbers_exposure_us / 1_000_000.0
            runtime_seconds = max(1, math.ceil(sequence_seconds))
    return runtime_seconds


def _to_pair_runtime_args(args: argparse.Namespace) -> list[str]:
    runtime_seconds = _pair_runtime_seconds(args)
    pair_args = [
        "--test",
        args.test,
        "--test-b",
        args.test_b,
        "--b-dot-x",
        str(args.b_dot_x),
        "--b-dot-y",
        str(args.b_dot_y),
        "--b-dot-radius",
        str(args.b_dot_radius),
        "--numbers",
        ",".join(str(number) for number in args.numbers),
        "--numbers-size-px",
        str(args.number_size_px),
        "--runtime-seconds",
        str(runtime_seconds),
        "--trigger-out-2-delay-fraction",
        str(args.trigger_out_2_delay_fraction),
    ]
    if args.numbers_exposure_us is not None:
        pair_args.extend(["--numbers-exposure-us", str(args.numbers_exposure_us)])
    if args.seq_utilization is not None:
        pair_args.extend(["--seq-utilization", str(args.seq_utilization)])
    if getattr(args, "dark_time_us", None) is not None:
        pair_args.extend(["--dark-time-us", str(args.dark_time_us)])
    if args.dmd_config is not None:
        pair_args.extend(["--dmd-config", args.dmd_config])
    if args.hz is not None:
        pair_args.extend(["--hz", str(args.hz)])
    for _ in range(args.verbose or 0):
        pair_args.append("-v")
    return pair_args


def _run_pair_with_callback(pair_args, before_start):
    pair_module = import_module("dmdcontrol.runtime.pair")
    return pair_module.run_with_before_start_callback(pair_args, before_start)


def live(args: argparse.Namespace) -> int:
    run = create_run_directory("sync-check", args.output_root, timestamp=args.timestamp)
    event_filter = event_noise_filter_config_from_args(args)
    capture = None
    writer = None
    recording = None
    capture_result = None
    artifact_summary = None
    event_records = []
    trigger_records = []
    accumulation_window_us = {"value": args.numbers_exposure_us}
    trigger_policy = {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "delay_fraction": args.trigger_out_2_delay_fraction,
    }
    metadata = {
        "mode": "sync-check",
        "dry_run": False,
        "command": sys.argv,
        "number_sequence": list(args.numbers),
        "number_size_px": args.number_size_px,
        "numbers_exposure_us": args.numbers_exposure_us,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "expected_trigger_count": expected_trigger_count(args),
        "seq_utilization": args.seq_utilization,
        "trigger_policy": trigger_policy,
        "bias_sensitivity": args.bias_sensitivity,
        "efps": args.efps,
        "polarity_mode": args.polarity_mode,
        "dark_time_us": args.dark_time_us,
        "event_noise_filter": event_noise_filter_metadata(event_filter),
        "save_filtered_events": args.save_filtered_events,
    }

    try:
        capture, writer, ready = _open_ready_camera(run, args)
        write_json(run.timing_path, trigger_policy)
        run.command_path.write_text(" ".join(sys.argv) + "\n", encoding="utf-8")
        run.log_path.write_text("live\n", encoding="utf-8")

        def before_start(context):
            nonlocal recording
            metadata.update({
                "camera_ready": _asdict(ready),
                "dmd_ready": True,
                "timing_a": context.get("state_a", {}).get("timing"),
                "timing_b": context.get("state_b", {}).get("timing"),
            })
            if accumulation_window_us["value"] is None:
                timing = context.get("state_a", {}).get("timing") or {}
                accumulation_window_us["value"] = timing.get("exposure_us")
            metadata["accumulation_window_us"] = accumulation_window_us["value"]
            if recording is None:
                recording = AsyncCapture(
                    capture,
                    writer,
                    expected_trigger_count=expected_trigger_count(args),
                    timeout_s=max(1, _pair_runtime_seconds(args)),
                    on_events=lambda batch: append_batch_records(event_records, batch, as_numpy=True),
                    on_triggers=lambda batch: append_batch_records(trigger_records, batch),
                    record_fn=record_until_trigger_count,
                )
                recording.start()
            write_run_metadata(
                run,
                metadata,
                artifacts=["raw.aedat4", "metadata.json"],
            )

        _run_pair_with_callback(_to_pair_runtime_args(args), before_start)
        if recording is not None:
            recording.stop()
            capture_result = recording.join()
            artifact_summary = write_capture_artifacts(
                run,
                events=event_records,
                triggers=trigger_records,
                resolution=tuple(ready.event_resolution),
                window_us=accumulation_window_us["value"] or 0,
                polarity_mode=args.polarity_mode,
                event_noise_filter=event_filter,
                save_filtered_events=args.save_filtered_events,
            )
            metadata["artifact_summary"] = artifact_summary
            if "event_noise_filter" in artifact_summary:
                metadata["event_noise_filter"] = artifact_summary["event_noise_filter"]
        return 0
    finally:
        if recording is not None and capture_result is None:
            recording.stop()
            try:
                capture_result = recording.join()
            except BaseException as exc:
                metadata["capture_error"] = repr(exc)
        if capture_result is not None:
            metadata["capture"] = _asdict(capture_result)
            artifacts = [
                "raw.aedat4",
                "metadata.json",
                "command.txt",
                "run.log",
                "timing.json",
            ]
            if artifact_summary is not None:
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
            write_run_metadata(
                run,
                metadata,
                artifacts=artifacts,
            )
        if writer is not None:
            del writer
        if capture is not None:
            del capture


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        dry_run(args)
        return 0
    return live(args)
