import json

import numpy as np
import pytest

from dmdcontrol.camera.event_records import BoundedArtifactBuffer
from dmdcontrol.camera.pair_capture import (
    _to_pair_runtime_args,
    build_parser,
    dry_run,
)


class FakeNumpyBatch:

    def __init__(self, array):
        self.array = array

    def numpy(self):
        return self.array


def test_bounded_artifact_buffer_snapshots_numpy_event_batches():
    source = np.array(
        [(100,
          2,
          1,
          True)],
        dtype=[
            ("timestamp",
             np.int64),
            ("x",
             np.int16),
            ("y",
             np.int16),
            ("polarity",
             np.bool_),
        ],
    )
    buffer = BoundedArtifactBuffer(max_rising_triggers=None, window_us=10)

    buffer.append_events(FakeNumpyBatch(source))
    source["timestamp"][0] = 999
    source["x"][0] = 9

    assert buffer.events[0]["timestamp"][0] == 100
    assert buffer.events[0]["x"][0] == 2
    assert not np.shares_memory(buffer.events[0], source)


def test_pair_capture_parser_accepts_requested_command_shape():
    args = build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            "a-kernel-b-static",
            "--test-b",
            "dot",
            "--b-dot-x",
            "960",
            "--b-dot-y",
            "540",
            "--b-dot-radius",
            "40",
            "--kernel-px",
            "1080",
            "--exposure-us",
            "3000",
            "--runtime-seconds",
            "999",
        ])

    assert args.dry_run_timing is True
    assert args.test == "a-kernel-b-static"
    assert args.test_b == "dot"
    assert args.b_dot_x == 960
    assert args.b_dot_y == 540
    assert args.b_dot_radius == 40
    assert args.kernel_px == 1080
    assert args.exposure_us == 3000
    assert args.runtime_seconds == 999


def test_pair_capture_parser_rejects_removed_kernel_exposure_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run-timing", "--kernel-exposure-us", "3000"])


def test_pair_capture_parser_rejects_removed_camera_open_method_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run-timing", "--camera-open-method", "modern"])


def test_pair_capture_parser_accepts_event_noise_filter_options():
    args = build_parser().parse_args(
        [
            "--dry-run-timing",
            "--event-noise-filter",
            "local-support",
            "--event-filter-delta-us",
            "50000",
            "--event-filter-window-px",
            "3",
            "--event-filter-threshold",
            "2",
            "--event-filter-polarity",
            "same",
            "--save-filtered-events",
        ])

    assert args.event_noise_filter == "local-support"
    assert args.event_filter_delta_us == 50000
    assert args.event_filter_window_px == 3
    assert args.event_filter_threshold == 2
    assert args.event_filter_polarity == "same"
    assert args.save_filtered_events is True


def test_pair_capture_parser_defaults_to_bounded_accumulation_artifacts():
    args = build_parser().parse_args(["--dry-run-timing"])

    assert args.max_accumulation_triggers == 512
    assert args.paired_startup_leader_vsyncs == 16


def test_pair_capture_parser_defaults_trigger_delay_to_zero():
    args = build_parser().parse_args(["--dry-run-timing"])

    assert args.trigger_out_2_rising_delay_us == 0


def test_pair_capture_parser_accepts_negative_trigger_rising_delay():
    args = build_parser().parse_args(
        ["--dry-run-timing", "--trigger-out-2-rising-delay-us", "-20"])

    assert args.trigger_out_2_rising_delay_us == -20


def test_pair_capture_runtime_args_forward_paired_startup_leader_vsyncs():
    args = build_parser().parse_args(
        [
            "--dry-run-timing",
            "--paired-startup-leader-vsyncs",
            "20",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[pair_args.index("--paired-startup-leader-vsyncs") + 1] == "20"


@pytest.mark.parametrize("value", ["-21", "19981"])
def test_pair_capture_parser_rejects_trigger_rising_delay_outside_effective_range(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--dry-run-timing", "--trigger-out-2-rising-delay-us", value])


def test_pair_capture_parser_rejects_removed_trigger_delay_fraction_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--dry-run-timing", "--trigger-out-2-delay-fraction", "0.05"])


def test_pair_capture_parser_rejects_removed_hz_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run-timing", "--hz", "120"])


@pytest.mark.parametrize("flag", ["--camera-usb-reset", "--no-camera-usb-reset"])
def test_pair_capture_parser_rejects_removed_usb_reset_flags(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run-timing", flag])


@pytest.mark.parametrize("flag", ["--camera-stream-rearm", "--camera-shutdown-streams"])
def test_pair_capture_parser_rejects_removed_camera_lifecycle_flags(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run-timing", flag])


def test_pair_capture_parser_uses_mentor_style_camera_lifecycle_by_default():
    args = build_parser().parse_args(["--dry-run-timing"])

    assert args.camera_flush_reads == 1
    assert args.camera_post_trigger_event_batches == 0


def test_pair_capture_parser_accepts_name_override_alias():
    args = build_parser().parse_args([
        "--dry-run-timing",
        "--name-override",
        "pair-test-run",
    ])

    assert args.timestamp == "pair-test-run"


def test_pair_capture_dry_run_creates_run_artifacts(tmp_path):
    argv = [
        "--dry-run-timing",
        "--output-root",
        str(tmp_path),
        "--timestamp",
        "20260527-120104",
        "--test",
        "a-kernel-b-static",
        "--test-b",
        "dot",
        "--b-dot-x",
        "960",
        "--b-dot-y",
        "540",
        "--b-dot-radius",
        "40",
        "--kernel-px",
        "1080",
        "--exposure-us",
        "3000",
        "--runtime-seconds",
        "999",
        "--trigger-out-2-rising-delay-us",
        "-20",
        "--dmd-config",
        "dmd_devices.json",
        "-vv",
    ]
    command_argv = ["python", "-m", "dmdcontrol", "camera", "pair-capture", *argv]
    args = build_parser().parse_args(argv)

    run = dry_run(args, command_argv=command_argv)

    assert run.path == tmp_path / "20260527-120104-pair-capture"
    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    timing = json.loads(run.timing_path.read_text(encoding="utf-8"))
    command = run.command_path.read_text(encoding="utf-8")
    log = run.log_path.read_text(encoding="utf-8")

    assert metadata["mode"] == "pair-capture"
    assert metadata["dry_run"] is True
    assert metadata["dmd"] == {
        "test": "a-kernel-b-static",
        "test_b": "dot",
        "b_dot_x": 960,
        "b_dot_y": 540,
        "b_dot_radius": 40,
        "kernel_px": 1080,
        "exposure_us": 3000,
        "runtime_seconds": 999,
        "paired_startup_leader_vsyncs": 16,
        "dmd_config": "dmd_devices.json",
    }
    assert metadata["requested_command_shape"] == [
        "--test",
        "a-kernel-b-static",
        "--test-b",
        "dot",
        "--b-dot-x",
        "960",
        "--b-dot-y",
        "540",
        "--b-dot-radius",
        "40",
        "--kernel-px",
        "1080",
        "--exposure-us",
        "3000",
        "--runtime-seconds",
        "999",
        "--paired-startup-leader-vsyncs",
        "16",
    ]
    assert metadata["expected_shape"] == {
        "kernel_count": 512,
        "input_image_count": None,
    }
    assert metadata["trigger_policy"] == {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": -20,
        "falling_delay_us": 0,
    }
    assert metadata["artifacts"] == ["metadata.json", "timing.json", "command.txt", "run.log"]
    assert metadata["command"] == command_argv
    assert timing == metadata["trigger_policy"]
    assert "--kernel-px 1080" in command
    assert "--trigger-out-2-rising-delay-us -20" in command
    assert "dry-run" in log


def test_pair_capture_runtime_args_forward_generic_exposure():
    args = build_parser().parse_args(
        [
            "--dry-run-timing",
            "--exposure-us",
            "3000",
            "--dark-time-us",
            "100",
            "--trigger-out-2-rising-delay-us",
            "-20",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert "--kernel-exposure-us" not in pair_args
    assert pair_args[pair_args.index("--exposure-us") + 1] == "3000"
    assert pair_args[pair_args.index("--dark-time-us") + 1] == "100"
    assert pair_args[pair_args.index("--trigger-out-2-rising-delay-us") + 1] == "-20"


def test_pair_capture_dry_run_records_accumulation_trigger_limit(tmp_path):
    args = build_parser().parse_args(
        [
            "--dry-run-timing",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260527-120109",
            "--max-accumulation-triggers",
            "64",
        ])

    run = dry_run(args)

    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert metadata["max_accumulation_triggers"] == 64


def test_pair_capture_dry_run_records_event_filter_config(tmp_path):
    args = build_parser().parse_args(
        [
            "--dry-run-timing",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260527-120108",
            "--event-noise-filter",
            "local-support",
            "--event-filter-delta-us",
            "50000",
            "--event-filter-window-px",
            "3",
            "--event-filter-threshold",
            "2",
            "--event-filter-polarity",
            "same",
        ])

    run = dry_run(args)

    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert metadata["event_noise_filter"] == {
        "algorithm":
        "centered-local-support",
        "delta_t_us":
        50000,
        "enabled":
        True,
        "note": (
            "Practical notebook-validated local support filter; "
            "not a source-faithful DV Runtime YNoise implementation."),
        "polarity":
        "same",
        "threshold":
        2,
        "window_px":
        3,
    }


def test_camera_pair_capture_cli_dry_run_creates_artifacts(tmp_path):
    from dmdcontrol.cli.main import main

    assert main(
        [
            "camera",
            "pair-capture",
            "--dry-run-timing",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260527-120105",
        ]) == 0

    metadata = json.loads(
        (tmp_path / "20260527-120105-pair-capture" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "pair-capture"
    assert metadata["expected_shape"]["kernel_count"] == 512
