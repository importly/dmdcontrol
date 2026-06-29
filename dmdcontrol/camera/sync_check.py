from __future__ import annotations

import argparse

from dmdcontrol.camera.capture import (
    AsyncCapture,
    append_batch_records,
    flush_stale_batches,
    record_until_trigger_count,
)
from dmdcontrol.camera.command_artifacts import camera_command_argv, command_text
from dmdcontrol.camera.local_support_filter import (
    add_event_noise_filter_arguments,
    event_noise_filter_config_from_args,
)
from dmdcontrol.camera.runs import (
    create_run_directory,
    final_capture_artifacts,
    metadata_dict,
    write_capture_artifacts,
    write_json,
    write_run_metadata,
)
from dmdcontrol.camera.session import (
    close_camera_resources,
    open_ready_camera as _open_ready_camera,
)
from dmdcontrol.camera.sync_check_metadata import (
    _sync_check_test_metadata,
    sync_check_metadata as _sync_check_metadata,
)
from dmdcontrol.camera.sync_check_runtime import (
    A_COUNT_B_STATIC_TEST,
    _pair_runtime_seconds,
    _requested_accumulation_window_us,
    _to_pair_runtime_args,
    _trigger_policy,
    expected_trigger_count,
)
from dmdcontrol.patterns.paired import MAX_COUNT_SEQUENCE_FRAMES
from dmdcontrol.runtime.count_slots import resolve_count_slots_per_frame
from dmdcontrol.support.argparse_types import (
    count_slots_per_frame,
    nonnegative_int,
    numbers_bitplane_order,
    positive_int,
    trigger_out_rising_delay_us,
)
from dmdcontrol.support.constants import BITPLANES

class SyncCheckArgumentParser(argparse.ArgumentParser):

    def parse_args(self, args=None, namespace=None):
        parsed = super().parse_args(args, namespace)
        try:
            _validate_count_mode_args(parsed, require_resolved_slots=False)
            _resolve_count_mode_slots(parsed)
            _validate_count_mode_args(parsed)
            _validate_numbers_mode_args(parsed)
        except ValueError as exc:
            self.error(str(exc))
        parsed.requested_accumulation_cycles = _requested_accumulation_cycles(parsed)
        return parsed


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


def _requested_accumulation_cycles(args: argparse.Namespace) -> int | None:
    if args.accumulation_cycles is not None:
        return args.accumulation_cycles
    if args.test == A_COUNT_B_STATIC_TEST:
        return None
    return 1


def _resolve_count_mode_slots(args: argparse.Namespace) -> None:
    if args.test != A_COUNT_B_STATIC_TEST:
        return
    mode = "auto" if args.count_slots_per_frame is None else "explicit"
    if mode == "auto":
        args.count_slots_per_frame = resolve_count_slots_per_frame(
            count_start=args.count_start,
            count_end=args.count_end,
            exposure_us=args.exposure_us,
            dark_time_us=args.dark_time_us,
            sequence_utilization=args.seq_utilization,
        )
    args.count_slots_per_frame_mode = mode


def _validate_count_mode_args(args: argparse.Namespace, *, require_resolved_slots: bool = True) -> None:
    if args.test != A_COUNT_B_STATIC_TEST:
        return
    if args.count_start > args.count_end:
        raise ValueError("--count-start must be <= --count-end")
    if args.count_slots_per_frame is None:
        if require_resolved_slots:
            raise ValueError("--count-slots-per-frame auto did not resolve")
        return
    if args.count_slots_per_frame <= 0 or args.count_slots_per_frame > BITPLANES:
        raise ValueError(f"--count-slots-per-frame must be in the range 1..{BITPLANES}")
    count_total = args.count_end - args.count_start + 1
    if count_total % args.count_slots_per_frame != 0:
        raise ValueError("count range length must be divisible by --count-slots-per-frame")
    frame_count = count_total // args.count_slots_per_frame
    if frame_count > MAX_COUNT_SEQUENCE_FRAMES:
        raise ValueError(
            f"a-count-b-static can span at most {MAX_COUNT_SEQUENCE_FRAMES} VSYNC frames")


def _validate_numbers_mode_args(args: argparse.Namespace) -> None:
    if args.test == A_COUNT_B_STATIC_TEST or args.numbers_bitplane_order is None:
        return
    if len(args.numbers_bitplane_order) != len(args.numbers):
        raise ValueError("--numbers-bitplane-order length must match --numbers length")
    if sorted(args.numbers_bitplane_order) != list(range(len(args.numbers))):
        raise ValueError(
            "--numbers-bitplane-order must be a zero-based permutation of --numbers slots")


def build_parser() -> argparse.ArgumentParser:
    parser = SyncCheckArgumentParser(
        prog="python -m dmdcontrol camera sync-check",
        description="Paired DMD + DVXplorer sync check.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-root", default=None)
    parser.add_argument(
        "--name-override",
        dest="timestamp",
        default=None,
        help="Override the generated run directory name prefix.",
    )
    parser.add_argument("--timestamp", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--number-size-px", type=positive_int, default=100)
    parser.add_argument("--numbers", type=parse_numbers, default=parse_numbers("1,2,3,4,5"))
    parser.add_argument(
        "--numbers-bitplane-order",
        type=numbers_bitplane_order,
        default=None,
        help=(
            "Zero-based bitplane indexes in chronological display order for numbers mode. "
            "Use 1,2,3,4,0 if --numbers 1,2,3,4,5 captures visually as 2,3,4,5,1."),
    )
    parser.add_argument(
        "--exposure-us",
        type=positive_int,
        default=None,
        help="Optional per-entry LUT exposure override in microseconds. "
        "Omit for the maximum safe exposure at the configured VSYNC.",
    )
    parser.add_argument("--count-start", type=positive_int, default=1)
    parser.add_argument("--count-end", type=positive_int, default=100)
    parser.add_argument("--count-slots-per-frame", type=count_slots_per_frame, default=None)
    parser.add_argument(
        "--trigger-out-2-rising-delay-us",
        type=trigger_out_rising_delay_us,
        default=0)
    parser.add_argument("--runtime-seconds", type=int, default=0)
    parser.add_argument(
        "--seq-utilization",
        type=float,
        default=None,
        help="Optional paired-runtime LUT budget utilization override. "
        "Use 1.0 only when intentionally using nearly the full VSYNC budget.",
    )
    parser.add_argument("--dmd-config", default=None)
    parser.add_argument("--test", default="a-numbers-b-static")
    parser.add_argument("--test-b", default="dot")
    parser.add_argument("--b-dot-x", type=int, default=960)
    parser.add_argument("--b-dot-y", type=int, default=540)
    parser.add_argument("--b-dot-radius", type=positive_int, default=20)
    parser.add_argument(
        "--bias-sensitivity",
        default="default",
        choices=["default",
                 "verylow",
                 "low",
                 "high",
                 "veryhigh"])
    parser.add_argument(
        "--efps",
        default="default",
        choices=["default",
                 "variable",
                 "variable_5000",
                 "constant_1000",
                 "constant_100"])
    parser.add_argument(
        "--polarity-mode",
        default="positive",
        choices=["positive",
                 "signed",
                 "ignore"])
    parser.add_argument(
        "--accumulation-start-offset-us",
        type=int,
        default=0,
        help="Shift each accumulation window relative to its trigger timestamp.",
    )
    parser.add_argument("--dark-time-us", type=int, default=None)
    parser.add_argument(
        "--camera-open-method",
        default="modern",
        choices=["modern",
                 "legacy"],
        help="Camera API used to open the device. Use legacy to mirror mentor CameraCapture code.",
    )
    parser.add_argument(
        "--camera-flush-reads",
        type=nonnegative_int,
        default=32,
        help="Maximum stale event/trigger batch reads to discard before capture.",
    )
    parser.add_argument(
        "--camera-post-trigger-event-batches",
        type=nonnegative_int,
        default=0,
        help="Number of extra event batches to read after the expected trigger count is reached.",
    )
    parser.add_argument(
        "--camera-stream-rearm",
        action="store_true",
        default=False,
        help="Diagnostic: cycle camera streams off/on before capture. Disabled by default.",
    )
    parser.add_argument(
        "--camera-shutdown-streams",
        action="store_true",
        default=False,
        help=
        "Diagnostic: stop camera streams before releasing the capture object. Disabled by default.",
    )
    parser.add_argument(
        "--accumulation-cycles",
        type=positive_int,
        default=None,
        help=(
            "Number of complete trigger cycles to use for derived accumulation artifacts. "
            "Numbers mode defaults to 1; count mode defaults to unlimited."),
    )
    add_event_noise_filter_arguments(parser)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def _run_pair_with_callback(pair_args, before_start):
    from dmdcontrol.runtime import pair as pair_module

    return pair_module.run_with_before_start_callback(pair_args, before_start)


def _validate_pair_dry_run_timing(args: argparse.Namespace) -> None:
    from dmdcontrol.runtime import pair as pair_module

    try:
        pair_module.main(["--dry-run-timing", *_to_pair_runtime_args(args)])
    except ValueError as exc:
        raise SystemExit(f"Invalid paired DMD timing: {exc}") from exc


def _copy_sweep_metadata(args: argparse.Namespace, metadata: dict[str, object]) -> None:
    for source_name, metadata_name in (
        ("sweep_id", "sweep_id"),
        ("sweep_index", "sweep_index"),
        ("sweep_repeat", "sweep_repeat"),
        ("sweep_manifest", "sweep_manifest"),
    ):
        if hasattr(args, source_name):
            metadata[metadata_name] = getattr(args, source_name)


def _start_recording(
    args,
    capture,
    writer,
    event_records,
    trigger_records,
    accumulation_window_us,
):
    recording = AsyncCapture(
        capture,
        writer,
        expected_trigger_count=None,
        timeout_s=max(1,
                      _pair_runtime_seconds(args)),
        on_events=lambda batch: append_batch_records(event_records, batch, as_numpy=True),
        on_triggers=lambda batch: append_batch_records(trigger_records, batch),
        record_fn=record_until_trigger_count,
        post_trigger_event_batches=args.camera_post_trigger_event_batches,
        post_trigger_event_time_us=accumulation_window_us or 0,
    )
    recording.start()
    return recording


def _update_before_start_metadata(metadata, ready, context, accumulation_window_us):
    metadata.update(
        {
            "camera_ready": metadata_dict(ready),
            "dmd_ready": True,
            "timing_a": context.get("state_a",
                                    {}).get("timing"),
            "timing_b": context.get("state_b",
                                    {}).get("timing"),
        })
    if accumulation_window_us["value"] is None:
        timing = context.get("state_a", {}).get("timing") or {}
        accumulation_window_us["value"] = timing.get("exposure_us")
    metadata["accumulation_window_us"] = accumulation_window_us["value"]


def _write_capture_artifacts_for_sync_check(
    args,
    run,
    ready,
    event_records,
    trigger_records,
    event_filter,
    accumulation_window_us,
):
    return write_capture_artifacts(
        run,
        events=event_records,
        triggers=trigger_records,
        resolution=tuple(ready.event_resolution),
        window_us=accumulation_window_us or 0,
        polarity_mode=args.polarity_mode,
        event_noise_filter=event_filter,
        save_filtered_events=args.save_filtered_events,
        trigger_cycle_length=expected_trigger_count(args),
        accumulation_cycles=args.requested_accumulation_cycles,
        window_start_offset_us=args.accumulation_start_offset_us,
        contact_sheet_columns=expected_trigger_count(args),
    )


def dry_run(args: argparse.Namespace, command_argv: list[str] | None = None):
    _validate_pair_dry_run_timing(args)
    run = create_run_directory("sync-check", args.output_root, timestamp=args.timestamp)
    event_filter = event_noise_filter_config_from_args(args)
    trigger_policy = _trigger_policy(args)
    command = command_argv or camera_command_argv("sync-check", None)
    metadata = _sync_check_metadata(args, event_filter, dry_run=True, command=command)
    write_json(run.timing_path, trigger_policy)
    write_run_metadata(
        run,
        metadata,
        artifacts=["metadata.json",
                   "timing.json",
                   "command.txt",
                   "run.log"],
    )
    run.command_path.write_text(
        command_text(command),
        encoding="utf-8",
    )
    run.log_path.write_text("dry-run\n", encoding="utf-8")
    return run


def live_capture(
    args: argparse.Namespace,
    run,
    capture,
    writer,
    ready,
    command_argv: list[str] | None = None,
) -> int:
    event_filter = event_noise_filter_config_from_args(args)
    recording = None
    capture_result = None
    artifact_summary = None
    event_records = []
    trigger_records = []
    accumulation_window_us = {"value": _requested_accumulation_window_us(args)}
    trigger_policy = _trigger_policy(args)
    metadata = _sync_check_metadata(
        args,
        event_filter,
        dry_run=False,
        command=command_argv or camera_command_argv("sync-check", None),
    )
    _copy_sweep_metadata(args, metadata)

    try:
        write_json(run.timing_path, trigger_policy)
        run.command_path.write_text(
            command_text(command_argv or camera_command_argv("sync-check", None)),
            encoding="utf-8",
        )
        run.log_path.write_text("live\n", encoding="utf-8")

        def before_start(context):
            nonlocal recording
            _update_before_start_metadata(metadata, ready, context, accumulation_window_us)
            metadata["camera_pre_capture_flush"] = flush_stale_batches(
                capture,
                reads=args.camera_flush_reads,
                include_triggers=True,
            )
            if recording is None:
                recording = _start_recording(
                    args,
                    capture,
                    writer,
                    event_records,
                    trigger_records,
                    accumulation_window_us["value"],
                )
            write_run_metadata(
                run,
                metadata,
                artifacts=["raw.aedat4",
                           "metadata.json"],
            )

        _run_pair_with_callback(_to_pair_runtime_args(args), before_start)
        if recording is not None:
            recording.stop()
            capture_result = recording.join()
            artifact_summary = _write_capture_artifacts_for_sync_check(
                args,
                run,
                ready,
                event_records,
                trigger_records,
                event_filter,
                accumulation_window_us["value"],
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
            metadata["capture"] = metadata_dict(capture_result)
            write_run_metadata(
                run,
                metadata,
                artifacts=final_capture_artifacts(artifact_summary),
            )
        if recording is not None:
            recording = None


def live(args: argparse.Namespace, command_argv: list[str] | None = None) -> int:
    run = create_run_directory("sync-check", args.output_root, timestamp=args.timestamp)
    capture = None
    writer = None
    try:
        capture, writer, ready = _open_ready_camera(run, args)
        return live_capture(args, run, capture, writer, ready, command_argv=command_argv)
    finally:
        resources = {"writer": writer, "capture": capture}
        close_camera_resources(
            resources,
            shutdown_streams=args.camera_shutdown_streams,
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command_argv = camera_command_argv("sync-check", argv)
    if args.dry_run:
        dry_run(args, command_argv=command_argv)
        return 0
    return live(args, command_argv=command_argv)
