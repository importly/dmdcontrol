import numpy as np
import pytest

from dmdcontrol.camera.event_records import BoundedArtifactBuffer
from dmdcontrol.camera.pair_capture import build_parser
from dmdcontrol.camera.sync_check_runtime import pair_runtime_args_from_capture


def _parse_args(args=None):
    return build_parser().parse_args(
        ["--exposure-us", "600", *(args or [])]
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
    args = _parse_args(
        [
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
        _parse_args(["--kernel-exposure-us", "3000"])


def test_pair_capture_parser_rejects_removed_camera_open_method_flag():
    with pytest.raises(SystemExit):
        _parse_args(["--camera-open-method", "modern"])


def test_pair_capture_parser_accepts_event_noise_filter_options():
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


def test_pair_capture_parser_defaults_to_bounded_accumulation_artifacts():
    args = _parse_args([])

    assert args.max_accumulation_triggers == 512
    assert args.paired_startup_leader_vsyncs == 16


def test_pair_capture_parser_defaults_trigger_delay_to_zero():
    args = _parse_args([])

    assert args.trigger_out_2_rising_delay_us == 0


def test_pair_capture_parser_accepts_negative_trigger_rising_delay():
    args = _parse_args(["--trigger-out-2-rising-delay-us", "-20"])

    assert args.trigger_out_2_rising_delay_us == -20


def test_pair_capture_runtime_args_forward_paired_startup_leader_vsyncs():
    args = _parse_args(
        [
            "--paired-startup-leader-vsyncs",
            "20",
        ]
    )

    pair_args = pair_runtime_args_from_capture(args)

    assert pair_args.paired_startup_leader_vsyncs == 20


@pytest.mark.parametrize("value", ["-21", "19981"])
def test_pair_capture_parser_rejects_trigger_rising_delay_outside_effective_range(value):
    with pytest.raises(SystemExit):
        _parse_args(["--trigger-out-2-rising-delay-us", value])


def test_pair_capture_parser_rejects_removed_trigger_delay_fraction_flag():
    with pytest.raises(SystemExit):
        _parse_args(["--trigger-out-2-delay-fraction", "0.05"])


def test_pair_capture_parser_rejects_removed_hz_flag():
    with pytest.raises(SystemExit):
        _parse_args(["--hz", "120"])


@pytest.mark.parametrize("flag", ["--camera-usb-reset", "--no-camera-usb-reset"])
def test_pair_capture_parser_rejects_removed_usb_reset_flags(flag):
    with pytest.raises(SystemExit):
        _parse_args([flag])


@pytest.mark.parametrize("flag", ["--camera-stream-rearm", "--camera-shutdown-streams"])
def test_pair_capture_parser_rejects_removed_camera_lifecycle_flags(flag):
    with pytest.raises(SystemExit):
        _parse_args([flag])


def test_pair_capture_parser_uses_mentor_style_camera_lifecycle_by_default():
    args = _parse_args([])

    assert args.camera_flush_reads == 1
    assert args.camera_post_trigger_event_batches == 0


def test_pair_capture_parser_accepts_name_override_alias():
    args = _parse_args([
        "--name-override",
        "pair-test-run",
    ])

    assert args.timestamp == "pair-test-run"


def test_pair_capture_runtime_args_forward_generic_exposure():
    args = _parse_args(
        [
            "--exposure-us",
            "3000",
            "--dark-time-us",
            "100",
            "--trigger-out-2-rising-delay-us",
            "-20",
        ]
    )

    pair_args = pair_runtime_args_from_capture(args)

    assert pair_args.exposure_us == 3000
    assert pair_args.dark_time_us == 100
    assert pair_args.trigger_out_2_rising_delay_us == -20