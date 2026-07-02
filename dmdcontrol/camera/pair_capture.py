from __future__ import annotations

import argparse

from dmdcontrol.camera.capture import (
    AsyncCapture,
    flush_stale_batches,
    record_until_trigger_count,
)
from dmdcontrol.camera.command_artifacts import camera_command_argv, command_text
from dmdcontrol.camera.event_records import BoundedArtifactBuffer
from dmdcontrol.camera.local_support_filter import (
    add_event_noise_filter_arguments,
    event_noise_filter_config_from_args,
    event_noise_filter_metadata,
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
from dmdcontrol.runtime.lifecycle import compute_trigger_out_2_timing
from dmdcontrol.support.argparse_types import (
    nonnegative_int,
    positive_int,
    trigger_out_rising_delay_us,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m dmdcontrol camera pair-capture",
        description="Capture paired camera data while running DMD pair patterns.",
    )
    parser.add_argument("--dry-run-timing", action="store_true")
    parser.add_argument("--output-root", default=None)
    parser.add_argument(
        "--name-override",
        dest="timestamp",
        default=None,
        help="Override the generated run directory name prefix.",
    )
    parser.add_argument("--timestamp", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--test", default="a-kernel-b-static")
    parser.add_argument("--test-b", default="dot")
    parser.add_argument("--b-dot-x", type=int, default=960)
    parser.add_argument("--b-dot-y", type=int, default=540)
    parser.add_argument("--b-dot-radius", type=positive_int, default=40)
    parser.add_argument("--kernel-px", type=positive_int, default=129)
    parser.add_argument("--exposure-us", type=positive_int, default=None)
    parser.add_argument("--runtime-seconds", type=positive_int, default=999)
    parser.add_argument(
        "--paired-startup-leader-vsyncs",
        type=nonnegative_int,
        default=16,
        help=(
            "Blank paired source VSYNCs after sequencer start before the first semantic frame. "
            "Forwarded to the paired DMD runtime and skipped in derived artifacts."),
    )
    parser.add_argument(
        "--trigger-out-2-rising-delay-us",
        type=trigger_out_rising_delay_us,
        default=0)
    parser.add_argument("--dmd-config", default=None)
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
    parser.add_argument("--dark-time-us", type=int, default=None)
    parser.add_argument(
        "--camera-flush-reads",
        type=nonnegative_int,
        default=1,
        help="Number of stale event/trigger batch reads to discard after opening the camera.",
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
        "--max-accumulation-triggers",
        type=positive_int,
        default=512,
        help=
        "Maximum rising triggers used for derived accumulation artifacts. Raw AEDAT recording is unchanged.",
    )
    add_event_noise_filter_arguments(parser)
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def expected_shape(args: argparse.Namespace) -> dict[str, int | None]:
    return {
        "kernel_count": 512 if args.test == "a-kernel-b-static" else None,
        "input_image_count": None,
    }


def requested_command_shape(args: argparse.Namespace) -> list[str]:
    shape = [
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
        "--kernel-px",
        str(args.kernel_px),
    ]
    if args.exposure_us is not None:
        shape.extend(["--exposure-us", str(args.exposure_us)])
    shape.extend(["--runtime-seconds", str(args.runtime_seconds)])
    shape.extend(["--paired-startup-leader-vsyncs", str(args.paired_startup_leader_vsyncs)])
    return shape


def dmd_config(args: argparse.Namespace) -> dict[str, int | str | None]:
    return {
        "test": args.test,
        "test_b": args.test_b,
        "b_dot_x": args.b_dot_x,
        "b_dot_y": args.b_dot_y,
        "b_dot_radius": args.b_dot_radius,
        "kernel_px": args.kernel_px,
        "exposure_us": args.exposure_us,
        "runtime_seconds": args.runtime_seconds,
        "paired_startup_leader_vsyncs": args.paired_startup_leader_vsyncs,
        "dmd_config": args.dmd_config,
    }


def trigger_policy(args: argparse.Namespace) -> dict[str, str | int]:
    timing = compute_trigger_out_2_timing(
        rising_delay_us=args.trigger_out_2_rising_delay_us)
    return {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": timing["rising_delay_us"],
        "falling_delay_us": timing["falling_delay_us"],
    }


def dry_run(args: argparse.Namespace, command_argv: list[str] | None = None):
    run = create_run_directory("pair-capture", args.output_root, timestamp=args.timestamp)
    policy = trigger_policy(args)
    event_filter = event_noise_filter_config_from_args(args)
    command = command_argv or camera_command_argv("pair-capture", None)
    metadata = {
        "mode": "pair-capture",
        "dry_run": True,
        "command": command,
        "dmd": dmd_config(args),
        "requested_command_shape": requested_command_shape(args),
        "expected_shape": expected_shape(args),
        "trigger_policy": policy,
        "bias_sensitivity": args.bias_sensitivity,
        "efps": args.efps,
        "polarity_mode": args.polarity_mode,
        "dark_time_us": args.dark_time_us,
        "camera_flush_reads": args.camera_flush_reads,
        "camera_post_trigger_event_batches": args.camera_post_trigger_event_batches,
        "camera_stream_rearm": args.camera_stream_rearm,
        "camera_shutdown_streams": args.camera_shutdown_streams,
        "max_accumulation_triggers": args.max_accumulation_triggers,
        "event_noise_filter": event_noise_filter_metadata(event_filter),
        "save_filtered_events": args.save_filtered_events,
    }
    write_json(run.timing_path, policy)
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


def _to_pair_runtime_args(args: argparse.Namespace) -> list[str]:
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
        "--kernel-px",
        str(args.kernel_px),
        "--runtime-seconds",
        str(args.runtime_seconds),
        "--paired-startup-leader-vsyncs",
        str(args.paired_startup_leader_vsyncs),
        "--trigger-out-2-rising-delay-us",
        str(args.trigger_out_2_rising_delay_us),
    ]
    if args.exposure_us is not None:
        pair_args.extend(["--exposure-us", str(args.exposure_us)])
    if getattr(args, "dark_time_us", None) is not None:
        pair_args.extend(["--dark-time-us", str(args.dark_time_us)])
    if args.dmd_config is not None:
        pair_args.extend(["--dmd-config", args.dmd_config])
    for _ in range(args.verbose or 0):
        pair_args.append("-v")
    return pair_args


def _accumulation_window_us(args: argparse.Namespace) -> int:
    if args.exposure_us is not None:
        return args.exposure_us
    return 0


def _run_pair_with_callback(pair_args, before_start):
    from dmdcontrol.runtime import pair as pair_module

    return pair_module.run_with_before_start_callback(pair_args, before_start)


def live(args: argparse.Namespace, command_argv: list[str] | None = None) -> int:
    run = create_run_directory("pair-capture", args.output_root, timestamp=args.timestamp)
    event_filter = event_noise_filter_config_from_args(args)
    capture = None
    writer = None
    recording = None
    capture_result = None
    artifact_summary = None
    artifact_buffer = BoundedArtifactBuffer(
        max_rising_triggers=args.max_accumulation_triggers,
        window_us=_accumulation_window_us(args),
    )
    metadata = {
        "mode": "pair-capture",
        "dry_run": False,
        "command": command_argv or camera_command_argv("pair-capture", None),
        "dmd": dmd_config(args),
        "requested_command_shape": requested_command_shape(args),
        "expected_shape": expected_shape(args),
        "trigger_policy": trigger_policy(args),
        "bias_sensitivity": args.bias_sensitivity,
        "efps": args.efps,
        "polarity_mode": args.polarity_mode,
        "dark_time_us": args.dark_time_us,
        "camera_flush_reads": args.camera_flush_reads,
        "camera_post_trigger_event_batches": args.camera_post_trigger_event_batches,
        "camera_stream_rearm": args.camera_stream_rearm,
        "camera_shutdown_streams": args.camera_shutdown_streams,
        "max_accumulation_triggers": args.max_accumulation_triggers,
        "event_noise_filter": event_noise_filter_metadata(event_filter),
        "save_filtered_events": args.save_filtered_events,
    }
    startup_leader_trigger_count = {"value": 0}

    try:
        capture, writer, ready = _open_ready_camera(run, args)
        write_json(run.timing_path, metadata["trigger_policy"])
        run.command_path.write_text(
            command_text(command_argv or camera_command_argv("pair-capture", None)),
            encoding="utf-8",
        )
        run.log_path.write_text("live\n", encoding="utf-8")

        def before_start(context):
            nonlocal recording
            startup_leader = context.get("startup_leader") or {}
            startup_leader_trigger_count["value"] = int(
                startup_leader.get("trigger_count") or 0)
            if args.max_accumulation_triggers is not None:
                artifact_buffer.max_rising_triggers = (
                    args.max_accumulation_triggers + startup_leader_trigger_count["value"])
            metadata.update(
                {
                    "camera_ready": metadata_dict(ready),
                    "dmd_ready": True,
                    "timing_a": context["state_a"]["timing"],
                    "timing_b": context["state_b"]["timing"],
                })
            if startup_leader:
                metadata["startup_leader"] = startup_leader
            if recording is None:
                recording = AsyncCapture(
                    capture,
                    writer,
                    expected_trigger_count=None,
                    timeout_s=max(1,
                                  args.runtime_seconds),
                    on_events=artifact_buffer.append_events,
                    on_triggers=artifact_buffer.append_triggers,
                    record_fn=record_until_trigger_count,
                    post_trigger_event_batches=args.camera_post_trigger_event_batches,
                )
                recording.start()
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
            artifact_summary = write_capture_artifacts(
                run,
                events=artifact_buffer.events,
                triggers=artifact_buffer.triggers,
                resolution=tuple(ready.event_resolution),
                window_us=_accumulation_window_us(args),
                polarity_mode=args.polarity_mode,
                event_noise_filter=event_filter,
                save_filtered_events=args.save_filtered_events,
                max_accumulation_triggers=args.max_accumulation_triggers,
                startup_leader_trigger_count=startup_leader_trigger_count["value"],
            )
            metadata["artifact_capture"] = artifact_buffer.to_metadata()
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
        resources = {"writer": writer, "capture": capture}
        writer = None
        capture = None
        close_camera_resources(
            resources,
            shutdown_streams=args.camera_shutdown_streams,
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command_argv = camera_command_argv("pair-capture", argv)
    if args.dry_run_timing:
        dry_run(args, command_argv=command_argv)
        return 0
    return live(args, command_argv=command_argv)
