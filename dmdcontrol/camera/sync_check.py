from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from dmdcontrol.runtime.pair import _run as run_pair_runtime

from dmdcontrol.camera.arguments import add_camera_performance_arguments
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
    sync_check_metadata as _sync_check_metadata,
)
from dmdcontrol.camera.sync_check_runtime import (
    A_COUNT_B_STATIC_TEST,
    _pair_runtime_seconds,
    trigger_policy,
    expected_trigger_count,
    pair_runtime_args_from_sync,
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


class SyncCheckArgumentParser(argparse.ArgumentParser):
    def parse_args(self, *args: Any, **kwargs: Any) -> argparse.Namespace:
        parsed = cast(argparse.Namespace, super().parse_args(*args, **kwargs))
        try:
            if parsed.test == A_COUNT_B_STATIC_TEST:
                slots_mode = (
                    "auto" if parsed.count_slots_per_frame is None else "explicit"
                )
                if parsed.count_slots_per_frame is None:
                    parsed.count_slots_per_frame = resolve_count_slots_per_frame(
                        count_start=parsed.count_start,
                        count_end=parsed.count_end,
                        exposure_us=parsed.exposure_us,
                        dark_time_us=parsed.dark_time_us,
                        count_blank_between_frames=parsed.count_blank_between_frames,
                        sequence_utilization=parsed.seq_utilization,
                    )
                parsed.count_slots_per_frame_mode = slots_mode
                CountSequenceConfig.from_args(parsed).validate_shape()
            elif parsed.count_blank_between_frames:
                raise ValueError(
                    "count blank insertion is only valid for --test a-count-b-static"
                )
        except ValueError as exc:
            self.error(str(exc))

        requested_cycles = parsed.accumulation_cycles
        if requested_cycles is None and parsed.test != A_COUNT_B_STATIC_TEST:
            requested_cycles = 1
        parsed.requested_accumulation_cycles = requested_cycles
        return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = SyncCheckArgumentParser(
        prog="python -m dmdcontrol camera sync-check",
        description="Paired DMD + DVXplorer sync check.",
    )
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
        required=True,
        help="Required per-entry LUT exposure in microseconds.",
    )
    parser.add_argument("--count-start", type=positive_int, default=DEFAULT_COUNT_START)
    parser.add_argument(
        "--count-end", type=positive_int, default=DEFAULT_SYNC_CHECK_COUNT_END
    )
    parser.add_argument(
        "--count-slots-per-frame", type=count_slots_per_frame, default=None
    )
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
        default=DEFAULT_TRIGGER_OUT_2_RISING_DELAY_US,
    )
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
            "Forwarded to the paired DMD runtime and skipped in derived artifacts."
        ),
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
    parser.add_argument(
        "--b-dot-radius", type=positive_int, default=DEFAULT_SYNC_CHECK_DOT_RADIUS_PX
    )
    add_camera_performance_arguments(parser)
    parser.add_argument(
        "--polarity-mode", default="positive", choices=["positive", "signed", "ignore"]
    )
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
            "Count mode defaults to unlimited."
        ),
    )
    add_event_noise_filter_arguments(parser)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


@dataclass
class SyncCheckCaptureSession:
    args: argparse.Namespace
    command: list[str]
    metadata: dict[str, object]
    startup_leader_trigger_count: int = 0
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
            command=command,
        )
        return cls(
            args=args,
            run=run,
            capture=capture,
            writer=writer,
            ready=ready,
            event_filter=event_filter,
            command=command,
            metadata=metadata,
            accumulation_window_us=args.exposure_us,
        )

    def write_initial_files(self) -> None:
        write_json(self.run.timing_path, trigger_policy(self.args))
        self.run.command_path.write_text(command_text(self.command), encoding="utf-8")
        self.run.log_path.write_text("live\n", encoding="utf-8")

    def before_pair_start(self, context: Mapping[str, object]) -> None:
        state_a = context.get("state_a")
        state_b = context.get("state_b")
        timing_a = state_a.get("timing") if isinstance(state_a, Mapping) else None
        timing_b = state_b.get("timing") if isinstance(state_b, Mapping) else None
        self.metadata.update(
            {
                "camera_ready": metadata_dict(self.ready),
                "dmd_ready": True,
                "timing_a": timing_a,
                "timing_b": timing_b,
                "accumulation_window_us": self.accumulation_window_us,
            }
        )

        startup_leader = context.get("startup_leader")
        if not isinstance(startup_leader, Mapping):
            startup_leader = {}
        if startup_leader:
            self.metadata["startup_leader"] = startup_leader
        self.startup_leader_trigger_count = int(
            startup_leader.get("trigger_count") or 0
        )
        display_sequence = context.get("display_sequence")
        if display_sequence is not None:
            self.metadata["display_sequence"] = display_sequence

        self.metadata["camera_pre_capture_flush"] = flush_stale_batches(
            self.capture,
            reads=self.args.camera_flush_reads,
            include_triggers=True,
        )
        if self.recording is None:
            self.recording = AsyncCapture(
                self.capture,
                self.writer,
                expected_trigger_count=None,
                timeout_s=max(1, _pair_runtime_seconds(self.args)),
                on_events=lambda batch: append_batch_records(
                    self.event_records, batch, as_numpy=True
                ),
                on_triggers=lambda batch: append_batch_records(
                    self.trigger_records, batch
                ),
                record_fn=record_until_trigger_count,
                post_trigger_event_batches=self.args.camera_post_trigger_event_batches,
                post_trigger_event_time_us=self.accumulation_window_us,
            )
            self.recording.start()
        write_run_metadata(
            self.run,
            self.metadata,
            artifacts=["raw.aedat4", "metadata.json"],
        )

    def complete_recording_and_artifacts(self) -> None:
        if self.recording is None:
            return
        self.recording.stop()
        self.capture_result = self.recording.join()
        trigger_count = expected_trigger_count(self.args)
        self.artifact_summary = write_capture_artifacts(
            self.run,
            events=self.event_records,
            triggers=self.trigger_records,
            resolution=tuple(self.ready.event_resolution),
            window_us=self.accumulation_window_us,
            polarity_mode=self.args.polarity_mode,
            event_noise_filter=self.event_filter,
            save_filtered_events=self.args.save_filtered_events,
            trigger_cycle_length=trigger_count,
            accumulation_cycles=self.args.requested_accumulation_cycles,
            window_start_offset_us=self.args.accumulation_start_offset_us,
            contact_sheet_columns=trigger_count,
            startup_leader_trigger_count=self.startup_leader_trigger_count,
        )
        self.metadata["artifact_summary"] = self.artifact_summary
        if "event_noise_filter" in self.artifact_summary:
            self.metadata["event_noise_filter"] = self.artifact_summary[
                "event_noise_filter"
            ]

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


def live_capture(
    args: argparse.Namespace,
    run: CameraRunDirectory,
    capture: object,
    writer: object,
    ready: CameraReadyState,
    command_argv: list[str] | None = None,
) -> int:
    session = SyncCheckCaptureSession.create(
        args, run, capture, writer, ready, command_argv
    )
    try:
        session.write_initial_files()
        run_pair_runtime(
            pair_runtime_args_from_sync(args), before_start=session.before_pair_start
        )
        session.complete_recording_and_artifacts()
        return 0
    finally:
        session.finalize()


def live(args: argparse.Namespace, command_argv: list[str] | None = None) -> int:
    run = create_run_directory("sync-check", args.output_root, timestamp=args.timestamp)

    capture, writer, ready = _open_ready_camera(run, args)

    return live_capture(
        args, run, capture, writer, ready, command_argv=command_argv
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command_argv = camera_command_argv("sync-check", argv)
    return live(args, command_argv=command_argv)
