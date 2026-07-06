from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from dmdcontrol.camera.capture import (
    AsyncCapture,
    CameraReadyState,
    CaptureResult,
    append_batch_records,
    flush_stale_batches,
    record_until_trigger_count,
)
from dmdcontrol.camera.command_artifacts import camera_command_argv, command_text
from dmdcontrol.camera.local_support_filter import (
    LocalSupportFilterConfig,
    add_event_noise_filter_arguments,
    event_noise_filter_config_from_args,
)
from dmdcontrol.camera.runs import (
    CameraRunDirectory,
    create_run_directory,
    final_capture_artifacts,
    metadata_dict,
    write_capture_artifacts,
    write_json,
    write_run_metadata,
)
from dmdcontrol.camera.session import close_camera_resources
from dmdcontrol.camera.session import open_ready_camera as _open_ready_camera
from dmdcontrol.camera.sync_check_metadata import (
    _sync_check_test_metadata as _sync_check_test_metadata,
)
from dmdcontrol.camera.sync_check_metadata import (
    sync_check_metadata as _sync_check_metadata,
)
from dmdcontrol.camera.sync_check_runtime import (
    A_COUNT_B_STATIC_TEST,
    _pair_runtime_seconds,
    _requested_accumulation_window_us,
    _trigger_policy,
    expected_trigger_count,
    pair_runtime_request_from_args,
)
from dmdcontrol.runtime.count_slots import (
    CountSequenceConfig,
    resolve_count_slots_per_frame,
)
from dmdcontrol.support.argparse_types import (
    count_slots_per_frame,
    nonnegative_int,
    positive_int,
    trigger_out_rising_delay_us,
    unit_interval_float,
)
from dmdcontrol.support.constants import (
    DEFAULT_CAMERA_POST_TRIGGER_EVENT_BATCHES,
    DEFAULT_COUNT_START,
    DEFAULT_PAIRED_STARTUP_LEADER_VSYNCS,
    DEFAULT_SYNC_CHECK_CAMERA_FLUSH_READS,
    DEFAULT_SYNC_CHECK_COUNT_END,
    DEFAULT_SYNC_CHECK_DOT_RADIUS_PX,
    DEFAULT_SYNC_CHECK_NUMBER_SIZE_PX,
    DEFAULT_SYNC_CHECK_RUNTIME_SECONDS,
    DEFAULT_TRIGGER_OUT_2_RISING_DELAY_US,
    DMD_CENTER_X,
    DMD_CENTER_Y,
)


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
            count_blank_between_frames=args.count_blank_between_frames,
            sequence_utilization=args.seq_utilization,
        )
    args.count_slots_per_frame_mode = mode


def _validate_count_mode_args(args: argparse.Namespace, *, require_resolved_slots: bool = True) -> None:
    if args.test != A_COUNT_B_STATIC_TEST:
        return
    if args.count_start > args.count_end:
        raise ValueError("--count-start must be <= --count-end")
    config = CountSequenceConfig.from_args(
        args,
        require_resolved_slots=require_resolved_slots,
    )
    if config is None:
        return
    config.validate_shape()


def _validate_count_blank_between_frames_mode(args: argparse.Namespace) -> None:
    if args.test != A_COUNT_B_STATIC_TEST and args.count_blank_between_frames:
        raise ValueError("count blank insertion is only valid for --test a-count-b-static")


class SyncCheckArgumentParser(argparse.ArgumentParser):

    def parse_args(self, *args: Any, **kwargs: Any) -> argparse.Namespace:
        parsed = cast(argparse.Namespace, super().parse_args(*args, **kwargs))
        try:
            _validate_count_blank_between_frames_mode(parsed)
            _validate_count_mode_args(parsed, require_resolved_slots=False)
            _resolve_count_mode_slots(parsed)
            _validate_count_mode_args(parsed)
        except ValueError as exc:
            self.error(str(exc))
        parsed.requested_accumulation_cycles = _requested_accumulation_cycles(parsed)
        return parsed


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
    parser.add_argument(
        "--number-size-px",
        type=positive_int,
        default=DEFAULT_SYNC_CHECK_NUMBER_SIZE_PX,
    )
    parser.add_argument(
        "--exposure-us",
        type=positive_int,
        default=None,
        help="Optional per-entry LUT exposure override in microseconds. "
        "Omit for the maximum safe exposure at the configured VSYNC.",
    )
    parser.add_argument("--count-start", type=positive_int, default=DEFAULT_COUNT_START)
    parser.add_argument("--count-end", type=positive_int, default=DEFAULT_SYNC_CHECK_COUNT_END)
    parser.add_argument("--count-slots-per-frame", type=count_slots_per_frame, default=None)
    parser.add_argument(
        "--count-blank-after-each-count",
        dest="count_blank_between_frames",
        action="store_true",
        help="Count mode only: insert an all-black A frame after each displayed count.",
    )
    parser.add_argument(
        "--count-blank-between-frames",
        dest="count_blank_between_frames",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--trigger-out-2-rising-delay-us",
        type=trigger_out_rising_delay_us,
        default=DEFAULT_TRIGGER_OUT_2_RISING_DELAY_US)
    parser.add_argument(
        "--runtime-seconds",
        type=nonnegative_int,
        default=DEFAULT_SYNC_CHECK_RUNTIME_SECONDS,
    )
    parser.add_argument(
        "--paired-startup-leader-vsyncs",
        type=nonnegative_int,
        default=DEFAULT_PAIRED_STARTUP_LEADER_VSYNCS,
        help=(
            "Blank paired source VSYNCs after sequencer start before the first semantic frame. "
            "Forwarded to the paired DMD runtime and skipped in derived artifacts."),
    )
    parser.add_argument(
        "--seq-utilization",
        type=unit_interval_float,
        default=None,
        help="Optional paired-runtime LUT budget utilization override. "
        "Use 1.0 only when intentionally using nearly the full VSYNC budget.",
    )
    parser.add_argument("--dmd-config", default=None)
    parser.add_argument("--test", default=A_COUNT_B_STATIC_TEST)
    parser.add_argument("--test-b", default="dot")
    parser.add_argument("--b-dot-x", type=int, default=DMD_CENTER_X)
    parser.add_argument("--b-dot-y", type=int, default=DMD_CENTER_Y)
    parser.add_argument("--b-dot-radius", type=positive_int, default=DEFAULT_SYNC_CHECK_DOT_RADIUS_PX)
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
    parser.add_argument("--dark-time-us", type=nonnegative_int, default=None)
    parser.add_argument(
        "--camera-flush-reads",
        type=nonnegative_int,
        default=DEFAULT_SYNC_CHECK_CAMERA_FLUSH_READS,
        help="Maximum stale event/trigger batch reads to discard before capture.",
    )
    parser.add_argument(
        "--camera-post-trigger-event-batches",
        type=nonnegative_int,
        default=DEFAULT_CAMERA_POST_TRIGGER_EVENT_BATCHES,
        help="Number of extra event batches to read after the expected trigger count is reached.",
    )
    parser.add_argument(
        "--accumulation-cycles",
        type=positive_int,
        default=None,
        help=(
            "Number of complete trigger cycles to use for derived accumulation artifacts. "
            "Count mode defaults to unlimited."),
    )
    add_event_noise_filter_arguments(parser)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def _run_pair_with_callback(pair_request, before_start):
    from dmdcontrol.runtime import pair as pair_module

    return pair_module.run_with_before_start_namespace(pair_request.to_namespace(), before_start)


def _validate_pair_dry_run_timing(args: argparse.Namespace) -> None:
    from dmdcontrol.runtime import pair as pair_module

    try:
        pair_module.run_namespace(
            pair_runtime_request_from_args(args).to_namespace(dry_run_timing=True))
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
    if accumulation_window_us is None:
        timing = context.get("state_a", {}).get("timing") or {}
        accumulation_window_us = timing.get("exposure_us")
    metadata["accumulation_window_us"] = accumulation_window_us
    startup_leader = context.get("startup_leader")
    if startup_leader is not None:
        metadata["startup_leader"] = startup_leader
    display_sequence = context.get("display_sequence")
    if display_sequence is not None:
        metadata["display_sequence"] = display_sequence
    return accumulation_window_us


def _write_capture_artifacts_for_sync_check(
    args,
    run,
    ready,
    event_records,
    trigger_records,
    event_filter,
    accumulation_window_us,
    startup_leader_trigger_count=0,
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
        startup_leader_trigger_count=startup_leader_trigger_count,
    )


@dataclass
class SyncCheckCaptureSession:
    args: argparse.Namespace
    run: CameraRunDirectory
    capture: object
    writer: object
    ready: CameraReadyState
    event_filter: LocalSupportFilterConfig
    command: list[str]
    metadata: dict[str, object]
    accumulation_window_us: int | None
    event_records: list = field(default_factory=list)
    trigger_records: list = field(default_factory=list)
    startup_leader_trigger_count: int = 0
    recording: AsyncCapture | None = None
    capture_result: CaptureResult | None = None
    artifact_summary: dict[str, object] | None = None

    @classmethod
    def create(
        cls,
        args: argparse.Namespace,
        run: CameraRunDirectory,
        capture: object,
        writer: object,
        ready: CameraReadyState,
        command_argv: list[str] | None,
    ) -> "SyncCheckCaptureSession":
        event_filter = event_noise_filter_config_from_args(args)
        command = command_argv or camera_command_argv("sync-check", None)
        metadata = _sync_check_metadata(
            args,
            event_filter,
            dry_run=False,
            command=command,
        )
        _copy_sweep_metadata(args, metadata)
        return cls(
            args=args,
            run=run,
            capture=capture,
            writer=writer,
            ready=ready,
            event_filter=event_filter,
            command=command,
            metadata=metadata,
            accumulation_window_us=_requested_accumulation_window_us(args),
        )

    def write_initial_files(self) -> None:
        write_json(self.run.timing_path, _trigger_policy(self.args))
        self.run.command_path.write_text(command_text(self.command), encoding="utf-8")
        self.run.log_path.write_text("live\n", encoding="utf-8")

    def before_pair_start(self, context: Mapping[str, object]) -> None:
        self.accumulation_window_us = _update_before_start_metadata(
            self.metadata,
            self.ready,
            context,
            self.accumulation_window_us,
        )
        startup_leader = context.get("startup_leader") or {}
        if not isinstance(startup_leader, Mapping):
            startup_leader = {}
        self.startup_leader_trigger_count = int(startup_leader.get("trigger_count") or 0)
        self.metadata["camera_pre_capture_flush"] = flush_stale_batches(
            self.capture,
            reads=self.args.camera_flush_reads,
            include_triggers=True,
        )
        if self.recording is None:
            self.recording = _start_recording(
                self.args,
                self.capture,
                self.writer,
                self.event_records,
                self.trigger_records,
                self.accumulation_window_us,
            )
        write_run_metadata(
            self.run,
            self.metadata,
            artifacts=["raw.aedat4",
                       "metadata.json"],
        )

    def complete_recording_and_artifacts(self) -> None:
        if self.recording is None:
            return
        self.recording.stop()
        self.capture_result = self.recording.join()
        self.artifact_summary = _write_capture_artifacts_for_sync_check(
            self.args,
            self.run,
            self.ready,
            self.event_records,
            self.trigger_records,
            self.event_filter,
            self.accumulation_window_us,
            startup_leader_trigger_count=self.startup_leader_trigger_count,
        )
        self.metadata["artifact_summary"] = self.artifact_summary
        if "event_noise_filter" in self.artifact_summary:
            self.metadata["event_noise_filter"] = self.artifact_summary["event_noise_filter"]

    def finalize(self) -> None:
        if self.recording is not None and self.capture_result is None:
            self.recording.stop()
            try:
                self.capture_result = self.recording.join()
            except BaseException as exc:
                self.metadata["capture_error"] = repr(exc)
        if self.capture_result is not None:
            self.metadata["capture"] = metadata_dict(self.capture_result)
            write_run_metadata(
                self.run,
                self.metadata,
                artifacts=final_capture_artifacts(self.artifact_summary),
            )
        self.recording = None


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
    session = SyncCheckCaptureSession.create(args, run, capture, writer, ready, command_argv)
    try:
        session.write_initial_files()
        _run_pair_with_callback(pair_runtime_request_from_args(args), session.before_pair_start)
        session.complete_recording_and_artifacts()
        return 0
    finally:
        session.finalize()


def live(args: argparse.Namespace, command_argv: list[str] | None = None) -> int:
    run = create_run_directory("sync-check", args.output_root, timestamp=args.timestamp)
    capture = None
    writer = None
    try:
        capture, writer, ready = _open_ready_camera(run, args)
        return live_capture(args, run, capture, writer, ready, command_argv=command_argv)
    finally:
        resources = {"writer": writer, "capture": capture}
        close_camera_resources(resources)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command_argv = camera_command_argv("sync-check", argv)
    if args.dry_run:
        dry_run(args, command_argv=command_argv)
        return 0
    return live(args, command_argv=command_argv)
