import importlib
import json
import shlex

import pytest

from dmdcontrol.camera.sync_check import (
    _sync_check_test_metadata,
    _to_pair_runtime_args,
    build_parser,
    dry_run,
    expected_trigger_count,
    parse_numbers,
)


def test_sync_check_has_focused_helper_modules():
    runtime = importlib.import_module("dmdcontrol.camera.sync_check_runtime")
    metadata = importlib.import_module("dmdcontrol.camera.sync_check_metadata")

    assert runtime._to_pair_runtime_args is _to_pair_runtime_args
    assert runtime.expected_trigger_count is expected_trigger_count
    assert metadata._sync_check_test_metadata is _sync_check_test_metadata
    assert hasattr(metadata, "sync_check_metadata")


def test_sync_check_parser_defaults_to_digits_one_through_five():
    args = build_parser().parse_args(["--dry-run"])

    assert args.numbers == [1, 2, 3, 4, 5]
    assert args.test == "a-numbers-b-static"
    assert args.test_b == "dot"
    assert args.number_size_px == 100
    assert args.b_dot_radius == 20
    assert args.accumulation_cycles is None
    assert args.accumulation_start_offset_us == 0
    assert args.paired_startup_leader_vsyncs == 16


def test_sync_check_numbers_mode_defaults_to_one_accumulation_cycle():
    args = build_parser().parse_args(["--dry-run"])

    assert args.requested_accumulation_cycles == 1


def test_sync_check_count_mode_does_not_limit_accumulation_cycles_by_default():
    args = build_parser().parse_args([
        "--dry-run",
        "--test",
        "a-count-b-static",
    ])

    assert args.requested_accumulation_cycles is None


def test_sync_check_parser_accepts_accumulation_cycle_options():
    args = build_parser().parse_args(
        [
            "--dry-run",
            "--accumulation-cycles",
            "2",
            "--accumulation-start-offset-us",
            "-50",
        ])

    assert args.accumulation_cycles == 2
    assert args.requested_accumulation_cycles == 2
    assert args.accumulation_start_offset_us == -50


@pytest.mark.parametrize("flag", ["--trigger-cluster-us", "--cycle-selection"])
def test_sync_check_parser_rejects_removed_trigger_selection_options(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", flag, "1"])


def test_sync_check_parser_rejects_removed_camera_open_method_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", "--camera-open-method", "modern"])


@pytest.mark.parametrize("value", ["", ",", "0", "1,10", "-1", "x"])
def test_sync_check_numbers_must_be_non_empty_decimal_digits(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", "--numbers", value])


@pytest.mark.parametrize("flag", ["--number-size-px", "--exposure-us"])
def test_sync_check_positive_numeric_options_are_validated(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", flag, "0"])


@pytest.mark.parametrize("flag", ["--numbers-exposure-us", "--count-exposure-us"])
def test_sync_check_parser_rejects_removed_exposure_flags(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", flag, "600"])


def test_sync_check_parser_defaults_trigger_rising_delay_to_zero():
    args = build_parser().parse_args(["--dry-run"])

    assert args.trigger_out_2_rising_delay_us == 0


def test_sync_check_parser_accepts_negative_trigger_rising_delay():
    args = build_parser().parse_args(
        ["--dry-run", "--trigger-out-2-rising-delay-us", "-20"])

    assert args.trigger_out_2_rising_delay_us == -20


@pytest.mark.parametrize("value", ["-21", "19981"])
def test_sync_check_parser_rejects_trigger_rising_delay_outside_effective_range(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--dry-run", "--trigger-out-2-rising-delay-us", value])


def test_sync_check_parser_rejects_removed_trigger_delay_fraction_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            ["--dry-run", "--trigger-out-2-delay-fraction", "0.05"])


def test_parse_numbers_accepts_comma_separated_digits():
    assert parse_numbers("1, 2,3") == [1, 2, 3]


def test_sync_check_runtime_args_use_requested_number_sequence():
    args = build_parser().parse_args(
        [
            "--numbers",
            "2,4,6",
            "--number-size-px",
            "123",
            "--runtime-seconds",
            "7",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[:4] == ["--test", "a-numbers-b-static", "--test-b", "dot"]
    assert "--checkerboard" not in pair_args
    assert "--trig2-frame-zero" not in pair_args
    assert pair_args[pair_args.index("--numbers") + 1] == "2,4,6"
    assert pair_args[pair_args.index("--numbers-size-px") + 1] == "123"
    assert pair_args[pair_args.index("--b-dot-radius") + 1] == "20"
    assert "--exposure-us" not in pair_args


def test_sync_check_runtime_args_forward_numbers_bitplane_order():
    args = build_parser().parse_args(
        [
            "--numbers",
            "1,2,3,4,5",
            "--numbers-bitplane-order",
            "1,2,3,4,0",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert args.numbers_bitplane_order == [1, 2, 3, 4, 0]
    assert pair_args[pair_args.index("--numbers-bitplane-order") + 1] == "1,2,3,4,0"


@pytest.mark.parametrize("value", ["4,2,3,1", "4,2,2,1,0", "5,2,3,1,0"])
def test_sync_check_numbers_bitplane_order_must_match_numbers_slots(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args([
            "--numbers",
            "1,2,3,4,5",
            "--numbers-bitplane-order",
            value,
        ])


def test_sync_check_runtime_args_pass_b_dot_geometry():
    args = build_parser().parse_args(
        [
            "--test",
            "a-numbers-b-static",
            "--test-b",
            "dot",
            "--b-dot-x",
            "955",
            "--b-dot-y",
            "535",
            "--b-dot-radius",
            "12",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[pair_args.index("--b-dot-x") + 1] == "955"
    assert pair_args[pair_args.index("--b-dot-y") + 1] == "535"
    assert pair_args[pair_args.index("--b-dot-radius") + 1] == "12"


def test_sync_check_runtime_args_allow_explicit_bitplane_exposure_override():
    args = build_parser().parse_args([
        "--exposure-us",
        "600",
        "--trigger-out-2-rising-delay-us",
        "-20",
    ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[pair_args.index("--exposure-us") + 1] == "600"
    assert pair_args[pair_args.index("--trigger-out-2-rising-delay-us") + 1] == "-20"


def test_sync_check_runtime_args_forward_paired_startup_leader_vsyncs():
    args = build_parser().parse_args(
        [
            "--paired-startup-leader-vsyncs",
            "20",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[pair_args.index("--paired-startup-leader-vsyncs") + 1] == "20"


def test_sync_check_parser_accepts_count_mode_options():
    args = build_parser().parse_args(
        [
            "--dry-run",
            "--test",
            "a-count-b-static",
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "1000",
        ])

    assert args.count_start == 1
    assert args.count_end == 100
    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"
    assert args.exposure_us == 4000


@pytest.mark.parametrize(
    "argv",
    [
        ["--test",
         "a-count-b-static",
         "--count-start",
         "5",
         "--count-end",
         "4"],
        [
            "--test",
            "a-count-b-static",
            "--count-start",
            "1",
            "--count-end",
            "5",
            "--count-slots-per-frame",
            "2"],
        ["--test",
         "a-count-b-static",
         "--count-end",
         "130",
         "--count-slots-per-frame",
         "2"],
        ["--test",
         "a-count-b-static",
         "--count-slots-per-frame",
         "25"],
    ],
)
def test_sync_check_parser_rejects_invalid_count_mode_options(argv):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", *argv])


def test_sync_check_count_mode_expects_one_trigger_per_count():
    args = build_parser().parse_args(
        [
            "--test",
            "a-count-b-static",
            "--count-start",
            "1",
            "--count-end",
            "100",
        ])

    assert expected_trigger_count(args) == 100


def test_sync_check_count_blank_between_frames_doubles_expected_triggers():
    args = build_parser().parse_args(
        [
            "--test",
            "a-count-b-static",
            "--count-start",
            "1",
            "--count-end",
            "4",
            "--count-slots-per-frame",
            "1",
            "--count-blank-between-frames",
        ])

    assert args.count_blank_between_frames is True
    assert expected_trigger_count(args) == 8


def test_sync_check_runtime_args_forward_count_options_without_numbers():
    args = build_parser().parse_args(
        [
            "--test",
            "a-count-b-static",
            "--test-b",
            "dot",
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--count-slots-per-frame",
            "2",
            "--exposure-us",
            "7000",
            "--number-size-px",
            "123",
            "--runtime-seconds",
            "2",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[:4] == ["--test", "a-count-b-static", "--test-b", "dot"]
    assert "--numbers" not in pair_args
    assert "--numbers-exposure-us" not in pair_args
    assert "--count-exposure-us" not in pair_args
    assert pair_args[pair_args.index("--count-start") + 1] == "1"
    assert pair_args[pair_args.index("--count-end") + 1] == "100"
    assert pair_args[pair_args.index("--count-slots-per-frame") + 1] == "2"
    assert pair_args[pair_args.index("--exposure-us") + 1] == "7000"
    assert pair_args[pair_args.index("--numbers-size-px") + 1] == "123"
    assert "--count-blank-between-frames" not in pair_args


def test_sync_check_runtime_args_forward_count_blank_between_frames():
    args = build_parser().parse_args(
        [
            "--test",
            "a-count-b-static",
            "--test-b",
            "dot",
            "--count-start",
            "1",
            "--count-end",
            "4",
            "--count-slots-per-frame",
            "1",
            "--count-blank-between-frames",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert "--count-blank-between-frames" in pair_args


def test_sync_check_runtime_args_auto_resolve_count_slots_from_timing():
    args = build_parser().parse_args(
        [
            "--test",
            "a-count-b-static",
            "--test-b",
            "dot",
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "1000",
            "--runtime-seconds",
            "2",
        ])

    pair_args = _to_pair_runtime_args(args)

    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"
    assert pair_args[pair_args.index("--count-slots-per-frame") + 1] == "2"


def test_sync_check_parser_accepts_event_noise_filter_options():
    args = build_parser().parse_args(
        [
            "--dry-run",
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


@pytest.mark.parametrize("flag", ["--camera-usb-reset", "--no-camera-usb-reset"])
def test_sync_check_parser_rejects_removed_usb_reset_flags(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", flag])


def test_sync_check_parser_rejects_removed_hz_flag():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", "--hz", "120"])


def test_sync_check_parser_uses_mentor_style_camera_lifecycle_by_default():
    args = build_parser().parse_args(["--dry-run"])

    assert args.camera_stream_rearm is False
    assert args.camera_shutdown_streams is False
    assert args.camera_flush_reads == 32
    assert args.camera_post_trigger_event_batches == 0


def test_sync_check_parser_accepts_name_override_alias():
    args = build_parser().parse_args([
        "--dry-run",
        "--name-override",
        "first-run",
    ])

    assert args.timestamp == "first-run"


def test_sync_check_dry_run_creates_run_artifacts(tmp_path):
    argv = [
        "--dry-run",
        "--output-root",
        str(tmp_path),
        "--timestamp",
        "20260527-120102",
        "--number-size-px",
        "420",
        "--numbers",
        "1,2,3,4,5",
        "--trigger-out-2-rising-delay-us",
        "-20",
        "--accumulation-start-offset-us",
        "-250",
    ]
    command_argv = ["python", "-m", "dmdcontrol", "camera", "sync-check", *argv]
    args = build_parser().parse_args(argv)

    run = dry_run(args, command_argv=command_argv)

    assert run.path == tmp_path / "20260527-120102-sync-check"
    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    timing = json.loads(run.timing_path.read_text(encoding="utf-8"))
    command = run.command_path.read_text(encoding="utf-8")
    log = run.log_path.read_text(encoding="utf-8")

    assert metadata["mode"] == "sync-check"
    assert metadata["dry_run"] is True
    assert metadata["number_sequence"] == [1, 2, 3, 4, 5]
    assert metadata["number_size_px"] == 420
    assert metadata["b_dot_radius"] == 20
    assert metadata["exposure_us"] is None
    assert metadata["expected_trigger_count"] == 5
    assert metadata["trigger_policy"] == {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": -20,
        "falling_delay_us": 0,
    }
    assert metadata["artifacts"] == ["metadata.json", "timing.json", "command.txt", "run.log"]
    assert metadata["command"] == command_argv
    assert timing == metadata["trigger_policy"]
    assert "--number-size-px 420" in command
    assert "--accumulation-start-offset-us -250" in command
    assert "dry-run" in log


@pytest.mark.parametrize(
    ("name_override", "accumulation_cycles"),
    [
        ("5nums_one_cycle_pretrigger250_onwindow", 1),
        ("5nums_30frames_pretrigger250_onwindow", 6),
    ],
)
def test_sync_check_dry_run_accepts_selected_five_number_commands(
    tmp_path,
    name_override,
    accumulation_cycles,
):
    argv = shlex.split(
        f"--dry-run --output-root {tmp_path.as_posix()} "
        f"--name-override {name_override} --test a-numbers-b-static --test-b dot "
        "--numbers 1,2,3,4,5 --number-size-px 100 "
        "--b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 "
        "--exposure-us 1900 --dark-time-us 1000 "
        "--trigger-out-2-rising-delay-us 0 --accumulation-start-offset-us -250 "
        "--runtime-seconds 1 --camera-flush-reads 0 "
        "--camera-post-trigger-event-batches 0 --polarity-mode ignore "
        f"--event-noise-filter none --save-filtered-events "
        f"--accumulation-cycles {accumulation_cycles} -v")
    command_argv = ["python", "-m", "dmdcontrol", "camera", "sync-check", *argv]

    run = dry_run(build_parser().parse_args(argv), command_argv=command_argv)

    assert run.path == tmp_path / f"{name_override}-sync-check"
    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    timing = json.loads(run.timing_path.read_text(encoding="utf-8"))
    command = run.command_path.read_text(encoding="utf-8")

    expected_metadata = {
        "dry_run": True,
        "test": "a-numbers-b-static",
        "number_sequence": [1, 2, 3, 4, 5],
        "number_size_px": 100,
        "b_dot_x": 960,
        "b_dot_y": 540,
        "b_dot_radius": 40,
        "exposure_us": 1900,
        "dark_time_us": 1000,
        "expected_trigger_count": 5,
        "accumulation_cycles": accumulation_cycles,
        "accumulation_start_offset_us": -250,
        "camera_flush_reads": 0,
        "camera_post_trigger_event_batches": 0,
        "polarity_mode": "ignore",
        "save_filtered_events": True,
    }
    assert {key: metadata[key] for key in expected_metadata} == expected_metadata
    assert metadata["event_noise_filter"]["algorithm"] == "none"
    assert metadata["event_noise_filter"]["enabled"] is False
    assert timing == {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "rising_delay_us": 0,
        "falling_delay_us": 20,
    }
    assert f"--name-override {name_override}" in command
    assert f"--accumulation-cycles {accumulation_cycles}" in command
    assert "--accumulation-start-offset-us -250" in command
    assert run.log_path.read_text(encoding="utf-8") == "dry-run\n"


def test_sync_check_dry_run_rejects_invalid_paired_lut_timing(tmp_path):
    argv = shlex.split(
        f"--dry-run --output-root {tmp_path.as_posix()} "
        "--test a-numbers-b-static --test-b dot "
        "--numbers 1,2,3,4,5 "
        "--exposure-us 4000 --dark-time-us 1000 "
        "--runtime-seconds 1")

    with pytest.raises(SystemExit, match="Invalid paired DMD timing: .*need .* usable"):
        dry_run(build_parser().parse_args(argv))

    assert list(tmp_path.iterdir()) == []


def test_sync_check_dry_run_records_event_filter_config(tmp_path):
    args = build_parser().parse_args(
        [
            "--dry-run",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260527-120107",
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


def test_sync_check_count_mode_dry_run_records_count_metadata(tmp_path):
    args = build_parser().parse_args(
        [
            "--dry-run",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260602-120100",
            "--test",
            "a-count-b-static",
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "1000",
        ])

    run = dry_run(args)

    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert metadata["test"] == "a-count-b-static"
    assert metadata["count_start"] == 1
    assert metadata["count_end"] == 100
    assert metadata["count_slots_per_frame"] == 2
    assert metadata["count_slots_per_frame_mode"] == "auto"
    assert metadata["count_blank_between_frames"] is False
    assert metadata["exposure_us"] == 4000
    assert metadata["expected_trigger_count"] == 100
    assert metadata["accumulation_window_us"] == 4000
    assert metadata["bitplane_count"] == 2


def test_sync_check_count_mode_dry_run_records_blank_between_frames_metadata(tmp_path):
    args = build_parser().parse_args(
        [
            "--dry-run",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260629-120100",
            "--test",
            "a-count-b-static",
            "--count-start",
            "1",
            "--count-end",
            "4",
            "--count-slots-per-frame",
            "1",
            "--count-blank-between-frames",
            "--exposure-us",
            "8000",
            "--seq-utilization",
            "1.0",
        ])

    run = dry_run(args)

    metadata = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    assert metadata["count_blank_between_frames"] is True
    assert metadata["expected_trigger_count"] == 8


def test_camera_sync_check_cli_dry_run_creates_artifacts(tmp_path):
    from dmdcontrol.cli.main import main

    assert main(
        [
            "camera",
            "sync-check",
            "--dry-run",
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260527-120103",
        ]) == 0

    metadata = json.loads(
        (tmp_path / "20260527-120103-sync-check" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["number_sequence"] == [1, 2, 3, 4, 5]


def test_live_capture_flushes_queued_triggers_before_recording(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dmdcontrol.camera.capture import CaptureResult
    from dmdcontrol.camera.runs import create_run_directory
    from dmdcontrol.camera import sync_check

    args = build_parser().parse_args(
        [
            "--output-root",
            str(tmp_path),
            "--timestamp",
            "20260604-120116",
            "--camera-flush-reads",
            "3",
        ])
    run = create_run_directory("sync-check", tmp_path, timestamp="20260604-120116")
    flush_calls = []

    monkeypatch.setattr(
        sync_check,
        "flush_stale_batches",
        lambda capture, reads, include_triggers=True: flush_calls.
        append({
            "reads": reads, "include_triggers": include_triggers}) or {"requested_reads": reads},
    )

    def fake_run_pair(_pair_args, before_start):
        before_start(
            {
                "state_a": {
                    "timing": {
                        "exposure_us": 1500}},
                "state_b": {
                    "timing": {
                        "exposure_us": 1500}},
            })
        return 0

    class FakeRecording:

        def stop(self):
            pass

        def join(self):
            return CaptureResult(
                trigger_count=0,
                event_batch_count=0,
                trigger_batch_count=0,
                timed_out=False,
            )

    monkeypatch.setattr(sync_check, "_run_pair_with_callback", fake_run_pair)
    monkeypatch.setattr(sync_check, "_start_recording", lambda *args, **kwargs: FakeRecording())
    monkeypatch.setattr(
        sync_check,
        "_write_capture_artifacts_for_sync_check", lambda *args, **kwargs: {
            "frame_artifacts": [],
            "filtered_frame_artifacts": [],
            "filtered_contact_sheet_artifact": None,
            "event_noise_filter": {
                "enabled": False}, })

    ready = SimpleNamespace(event_resolution=(320, 240))

    assert sync_check.live_capture(args, run, object(), object(), ready) == 0
    assert flush_calls == [{"reads": 3, "include_triggers": True}]
