import json

import pytest

from dmdcontrol.camera.sync_check import (
    _to_pair_runtime_args,
    build_parser,
    dry_run,
    parse_numbers,
)


def test_sync_check_parser_defaults_to_digits_one_through_five():
    args = build_parser().parse_args(["--dry-run"])

    assert args.numbers == [1, 2, 3, 4, 5]
    assert args.test == "a-numbers-b-static"
    assert args.test_b == "dot"
    assert args.number_size_px == 100
    assert args.b_dot_radius == 20


@pytest.mark.parametrize("value", ["", ",", "0", "1,10", "-1", "x"])
def test_sync_check_numbers_must_be_non_empty_decimal_digits(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", "--numbers", value])


@pytest.mark.parametrize("flag", ["--number-size-px", "--numbers-exposure-us"])
def test_sync_check_positive_numeric_options_are_validated(flag):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--dry-run", flag, "0"])


def test_parse_numbers_accepts_comma_separated_digits():
    assert parse_numbers("1, 2,3") == [1, 2, 3]


def test_sync_check_runtime_args_use_requested_number_sequence():
    args = build_parser().parse_args([
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
    assert "--numbers-exposure-us" not in pair_args


def test_sync_check_runtime_args_pass_b_dot_geometry():
    args = build_parser().parse_args([
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
        "--numbers-exposure-us",
        "600",
    ])

    pair_args = _to_pair_runtime_args(args)

    assert pair_args[pair_args.index("--numbers-exposure-us") + 1] == "600"


def test_sync_check_parser_accepts_event_noise_filter_options():
    args = build_parser().parse_args([
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


def test_sync_check_parser_does_not_reset_camera_usb_by_default():
    args = build_parser().parse_args(["--dry-run"])
    enabled = build_parser().parse_args(["--dry-run", "--camera-usb-reset"])
    disabled = build_parser().parse_args(["--dry-run", "--no-camera-usb-reset"])

    assert args.camera_usb_reset is False
    assert enabled.camera_usb_reset is True
    assert disabled.camera_usb_reset is False


def test_sync_check_parser_uses_mentor_style_camera_lifecycle_by_default():
    args = build_parser().parse_args(["--dry-run"])

    assert args.camera_stream_rearm is False
    assert args.camera_shutdown_streams is False
    assert args.camera_flush_reads == 1
    assert args.camera_post_trigger_event_batches == 0


def test_sync_check_parser_accepts_power_cycle_command():
    args = build_parser().parse_args([
        "--dry-run",
        "--camera-power-cycle-command",
        "uhubctl -l 1-2 -p 3 -a cycle -d 2",
    ])

    assert args.camera_power_cycle_command == "uhubctl -l 1-2 -p 3 -a cycle -d 2"


def test_sync_check_parser_accepts_name_override_alias():
    args = build_parser().parse_args([
        "--dry-run",
        "--name-override",
        "first-run",
    ])

    assert args.timestamp == "first-run"


def test_sync_check_dry_run_creates_run_artifacts(tmp_path):
    args = build_parser().parse_args([
        "--dry-run",
        "--output-root",
        str(tmp_path),
        "--timestamp",
        "20260527-120102",
        "--number-size-px",
        "420",
        "--numbers",
        "1,2,3,4,5",
        "--trigger-out-2-delay-fraction",
        "0.05",
    ])

    run = dry_run(args)

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
    assert metadata["numbers_exposure_us"] is None
    assert metadata["expected_trigger_count"] == 5
    assert metadata["trigger_policy"] == {
        "channel": "TRIG_OUT_2",
        "edge": "rising",
        "delay_fraction": 0.05,
    }
    assert metadata["artifacts"] == ["metadata.json", "timing.json", "command.txt", "run.log"]
    assert timing == metadata["trigger_policy"]
    assert "dmdcontrol camera sync-check --dry-run" in command
    assert "dry-run" in log


def test_sync_check_dry_run_records_event_filter_config(tmp_path):
    args = build_parser().parse_args([
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
        "algorithm": "centered-local-support",
        "delta_t_us": 50000,
        "enabled": True,
        "note": (
            "Practical notebook-validated local support filter; "
            "not a source-faithful DV Runtime YNoise implementation."
        ),
        "polarity": "same",
        "threshold": 2,
        "window_px": 3,
    }


def test_camera_sync_check_cli_dry_run_creates_artifacts(tmp_path):
    from dmdcontrol.cli.main import main

    assert main([
        "camera",
        "sync-check",
        "--dry-run",
        "--output-root",
        str(tmp_path),
        "--timestamp",
        "20260527-120103",
    ]) == 0

    metadata = json.loads((tmp_path / "20260527-120103-sync-check" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["number_sequence"] == [1, 2, 3, 4, 5]
