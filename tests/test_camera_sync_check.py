import importlib

import pytest

from dmdcontrol.camera.local_support_filter import LocalSupportFilterConfig
from dmdcontrol.camera.sync_check import (
    build_parser,
    expected_trigger_count,
)
from dmdcontrol.camera.sync_check_metadata import (
    _sync_check_test_metadata,
    sync_check_metadata,
)
from dmdcontrol.camera.sync_check_runtime import (
    PairRuntimeRequest,
    pair_runtime_request_from_args,
)


def test_sync_check_has_focused_helper_modules():
    runtime = importlib.import_module("dmdcontrol.camera.sync_check_runtime")
    metadata = importlib.import_module("dmdcontrol.camera.sync_check_metadata")

    assert hasattr(runtime, "pair_runtime_request_from_args")
    assert runtime.expected_trigger_count is expected_trigger_count
    assert metadata._sync_check_test_metadata is _sync_check_test_metadata
    assert hasattr(metadata, "sync_check_metadata")


def _parse_args(args=None):
    return build_parser().parse_args(
        ["--exposure-us", "600", *(args or [])]
    )


def test_sync_check_parser_requires_exposure():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def _pair_runtime_argv(args):
    return pair_runtime_request_from_args(args).to_argv()


def _count_args(*args):
    return _parse_args(["--test", "a-count-b-static", *args])


def test_sync_check_parser_defaults_to_count_recipe():
    args = _parse_args([])

    assert args.test == "a-count-b-static"
    assert args.test_b == "dot"
    assert args.count_start == 1
    assert args.count_end == 5
    assert args.count_slots_per_frame == 5
    assert args.count_slots_per_frame_mode == "auto"
    assert args.number_size_px == 100
    assert args.b_dot_radius == 20
    assert args.accumulation_cycles is None
    assert args.accumulation_start_offset_us == 0
    assert args.paired_startup_leader_vsyncs == 16



def test_sync_check_count_mode_does_not_limit_accumulation_cycles_by_default():
    args = _parse_args([])

    assert args.requested_accumulation_cycles is None


def test_sync_check_parser_accepts_accumulation_cycle_options():
    args = _parse_args(
        [
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
        _parse_args([flag, "1"])


def test_sync_check_parser_rejects_removed_camera_open_method_flag():
    with pytest.raises(SystemExit):
        _parse_args(["--camera-open-method", "modern"])


@pytest.mark.parametrize("flag", ["--numbers", "--numbers-bitplane-order"])
def test_sync_check_parser_rejects_removed_numbers_flags(flag):
    with pytest.raises(SystemExit):
        _parse_args([flag, "1,2,3"])


@pytest.mark.parametrize("flag", ["--number-size-px", "--exposure-us"])
def test_sync_check_positive_numeric_options_are_validated(flag):
    with pytest.raises(SystemExit):
        _parse_args([flag, "0"])


@pytest.mark.parametrize("flag", ["--numbers-exposure-us", "--count-exposure-us"])
def test_sync_check_parser_rejects_removed_exposure_flags(flag):
    with pytest.raises(SystemExit):
        _parse_args([flag, "600"])


def test_sync_check_parser_defaults_trigger_rising_delay_to_zero():
    args = _parse_args([])

    assert args.trigger_out_2_rising_delay_us == 0


def test_sync_check_parser_accepts_negative_trigger_rising_delay():
    args = _parse_args(["--trigger-out-2-rising-delay-us", "-20"])

    assert args.trigger_out_2_rising_delay_us == -20


@pytest.mark.parametrize("value", ["-21", "19981"])
def test_sync_check_parser_rejects_trigger_rising_delay_outside_effective_range(value):
    with pytest.raises(SystemExit):
        _parse_args(["--trigger-out-2-rising-delay-us", value])


def test_sync_check_parser_rejects_removed_trigger_delay_fraction_flag():
    with pytest.raises(SystemExit):
        _parse_args(["--trigger-out-2-delay-fraction", "0.05"])


def test_sync_check_runtime_args_use_default_count_recipe():
    args = _parse_args(
        [
            "--number-size-px",
            "123",
            "--runtime-seconds",
            "7",
        ])

    pair_args = _pair_runtime_argv(args)

    assert pair_args[:4] == ["--test", "a-count-b-static", "--test-b", "dot"]
    assert "--trig2-frame-zero" not in pair_args
    assert "--numbers" not in pair_args
    assert "--numbers-bitplane-order" not in pair_args
    assert pair_args[pair_args.index("--count-start") + 1] == "1"
    assert pair_args[pair_args.index("--count-end") + 1] == "5"
    assert pair_args[pair_args.index("--count-slots-per-frame") + 1] == "5"
    assert pair_args[pair_args.index("--numbers-size-px") + 1] == "123"
    assert pair_args[pair_args.index("--b-dot-radius") + 1] == "20"
    assert pair_args[pair_args.index("--exposure-us") + 1] == "600"


def test_sync_check_runtime_args_pass_b_dot_geometry():
    args = _parse_args(
        [
            "--test",
            "a-count-b-static",
            "--test-b",
            "dot",
            "--b-dot-x",
            "955",
            "--b-dot-y",
            "535",
            "--b-dot-radius",
            "12",
        ])

    pair_args = _pair_runtime_argv(args)

    assert pair_args[pair_args.index("--b-dot-x") + 1] == "955"
    assert pair_args[pair_args.index("--b-dot-y") + 1] == "535"
    assert pair_args[pair_args.index("--b-dot-radius") + 1] == "12"


def test_sync_check_runtime_args_allow_explicit_bitplane_exposure_override():
    args = _parse_args([
        "--exposure-us",
        "2900",
        "--trigger-out-2-rising-delay-us",
        "-20",
    ])

    pair_args = _pair_runtime_argv(args)

    assert pair_args[pair_args.index("--exposure-us") + 1] == "2900"
    assert pair_args[pair_args.index("--trigger-out-2-rising-delay-us") + 1] == "-20"


def test_sync_check_runtime_args_forward_paired_startup_leader_vsyncs():
    args = _parse_args(["--paired-startup-leader-vsyncs", "20"])

    pair_args = _pair_runtime_argv(args)

    assert pair_args[pair_args.index("--paired-startup-leader-vsyncs") + 1] == "20"


def test_sync_check_parser_accepts_count_mode_options():
    args = _count_args(
        "--count-start",
        "1",
        "--count-end",
        "100",
        "--exposure-us",
        "4000",
        "--dark-time-us",
        "1000",
    )

    assert args.count_start == 1
    assert args.count_end == 100
    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"
    assert args.exposure_us == 4000


@pytest.mark.parametrize(
    "argv",
    [
        ["--count-start", "5", "--count-end", "4"],
        ["--count-start", "1", "--count-end", "5", "--count-slots-per-frame", "2"],
        ["--count-end", "258", "--count-slots-per-frame", "2"],
        ["--count-slots-per-frame", "25"],
    ],
)
def test_sync_check_parser_rejects_invalid_count_mode_options(argv):
    with pytest.raises(SystemExit):
        _count_args(*argv)


def test_sync_check_count_mode_expects_one_trigger_per_count():
    args = _count_args("--count-start", "1", "--count-end", "100")

    assert expected_trigger_count(args) == 100


def test_sync_check_count_blank_between_frames_doubles_expected_triggers():
    args = _count_args(
        "--count-start",
        "1",
        "--count-end",
        "4",
        "--count-slots-per-frame",
        "1",
        "--count-blank-between-frames",
    )

    assert args.count_blank_between_frames is True
    assert expected_trigger_count(args) == 8


def test_sync_check_count_blank_after_each_count_alias_doubles_expected_triggers():
    args = _count_args(
        "--count-start",
        "1",
        "--count-end",
        "4",
        "--count-slots-per-frame",
        "1",
        "--count-blank-after-each-count",
    )

    assert args.count_blank_between_frames is True
    assert expected_trigger_count(args) == 8


def test_sync_check_metadata_records_count_timing_lut_and_capture_policy():
    args = _count_args(
        "--test-b",
        "dot",
        "--count-start",
        "1",
        "--count-end",
        "60",
        "--count-slots-per-frame",
        "1",
        "--count-blank-after-each-count",
        "--exposure-us",
        "16000",
        "--seq-utilization",
        "1.0",
        "--trigger-out-2-rising-delay-us",
        "250",
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
    )
    event_filter = LocalSupportFilterConfig(
        enabled=True,
        delta_t_us=50000,
        window_px=3,
        threshold=2,
        polarity="same",
    )

    metadata = sync_check_metadata(args, event_filter, command=["sync-check"])

    assert metadata["mode"] == "sync-check"
    assert metadata["test"] == "a-count-b-static"
    assert metadata["test_b"] == "dot"
    assert metadata["command"] == ["sync-check"]
    assert metadata["expected_trigger_count"] == 120
    assert metadata["count_start"] == 1
    assert metadata["count_end"] == 60
    assert metadata["count_slots_per_frame"] == 1
    assert metadata["count_slots_per_frame_mode"] == "explicit"
    assert metadata["count_blank_between_frames"] is True
    assert metadata["count_blank_after_each_count"] is True
    assert metadata["count_lut_entries_per_frame"] == 1
    assert metadata["bitplane_count"] == 1
    assert metadata["accumulation_window_us"] == 16000
    assert metadata["trigger_policy"] == {
        "channel": "TRIG_OUT_2",
        "source_dmd": "A",
        "edge": "rising",
        "rising_delay_us": 250,
        "falling_delay_us": 270,
    }
    assert metadata["event_noise_filter"]["enabled"] is True
    assert metadata["event_noise_filter"]["algorithm"] == "centered-local-support"
    assert metadata["save_filtered_events"] is True


def test_sync_check_runtime_args_forward_count_options_without_numbers():
    args = _count_args(
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
    )

    pair_args = _pair_runtime_argv(args)

    assert pair_args[:4] == ["--test", "a-count-b-static", "--test-b", "dot"]
    assert "--numbers" not in pair_args
    assert "--numbers-exposure-us" not in pair_args
    assert "--count-exposure-us" not in pair_args
    assert pair_args[pair_args.index("--count-start") + 1] == "1"
    assert pair_args[pair_args.index("--count-end") + 1] == "100"
    assert pair_args[pair_args.index("--count-slots-per-frame") + 1] == "2"
    assert pair_args[pair_args.index("--exposure-us") + 1] == "7000"
    assert pair_args[pair_args.index("--numbers-size-px") + 1] == "123"
    assert "--count-blank-after-each-count" not in pair_args
    assert "--count-blank-between-frames" not in pair_args


def test_sync_check_runtime_args_forward_count_blank_between_frames():
    args = _count_args(
        "--test-b",
        "dot",
        "--count-start",
        "1",
        "--count-end",
        "4",
        "--count-slots-per-frame",
        "1",
        "--count-blank-between-frames",
    )

    pair_args = _pair_runtime_argv(args)

    assert "--count-blank-after-each-count" in pair_args


def test_sync_check_runtime_args_auto_resolve_count_slots_from_timing():
    args = _count_args(
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
    )

    pair_args = _pair_runtime_argv(args)

    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"
    assert pair_args[pair_args.index("--count-slots-per-frame") + 1] == "2"


def test_sync_check_pair_runtime_request_keeps_auto_count_slots_for_internal_runtime():
    args = _count_args(
        "--test-b",
        "dot",
        "--count-start",
        "1",
        "--count-end",
        "60",
        "--exposure-us",
        "8000",
        "--seq-utilization",
        "1.0",
    )

    request = pair_runtime_request_from_args(args)
    pair_namespace = request.to_namespace()
    request_argv = request.to_argv()

    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"
    assert pair_namespace.count_slots_per_frame is None
    assert pair_namespace.count_slots_per_frame_mode == "auto"
    assert request_argv[request_argv.index("--count-slots-per-frame") + 1] == "2"


def test_sync_check_parser_accepts_event_noise_filter_options():
    args = _parse_args(
        [
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
        _parse_args([flag])


def test_sync_check_parser_rejects_removed_hz_flag():
    with pytest.raises(SystemExit):
        _parse_args(["--hz", "120"])


@pytest.mark.parametrize("flag", ["--camera-stream-rearm", "--camera-shutdown-streams"])
def test_sync_check_parser_rejects_removed_camera_lifecycle_flags(flag):
    with pytest.raises(SystemExit):
        _parse_args([flag])


def test_sync_check_parser_uses_mentor_style_camera_lifecycle_by_default():
    args = _parse_args([])

    assert args.camera_flush_reads == 32
    assert args.camera_post_trigger_event_batches == 0


def test_sync_check_parser_accepts_name_override_alias():
    args = _parse_args(["--name-override", "first-run"])

    assert args.timestamp == "first-run"


def test_live_capture_flushes_queued_triggers_before_recording(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from dmdcontrol.camera import sync_check
    from dmdcontrol.camera.capture import CaptureResult
    from dmdcontrol.camera.runs import create_run_directory

    args = _parse_args(
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
        lambda capture, reads, include_triggers=True: flush_calls.append(
            {"reads": reads, "include_triggers": include_triggers}) or {"requested_reads": reads},
    )

    def fake_run_pair(pair_request, before_start):
        assert isinstance(pair_request, PairRuntimeRequest)
        before_start(
            {
                "state_a": {"timing": {"exposure_us": 1500}},
                "state_b": {"timing": {"exposure_us": 1500}},
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
            "event_noise_filter": {"enabled": False},
        })

    ready = SimpleNamespace(event_resolution=(320, 240))

    assert sync_check.live_capture(args, run, object(), object(), ready) == 0
    assert flush_calls == [{"reads": 3, "include_triggers": True}]