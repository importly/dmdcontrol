import types

import numpy as np
import pytest

from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    A_NUMBERS_B_STATIC_PAIR_TEST,
    STATIC_IMAGES_PAIR_TEST,
)
from dmdcontrol.runtime.pair import _lut_override, main


def test_pair_runtime_parser_defaults_trigger_delay_to_zero():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(["--dry-run-timing"])

    assert args.trigger_out_2_rising_delay_us == 0


def test_pair_runtime_parser_accepts_negative_trigger_rising_delay():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        ["--dry-run-timing", "--trigger-out-2-rising-delay-us", "-20"])

    assert args.trigger_out_2_rising_delay_us == -20


@pytest.mark.parametrize("value", ["-21", "19981"])
def test_pair_runtime_parser_rejects_trigger_rising_delay_outside_effective_range(value):
    from dmdcontrol.runtime import pair

    with pytest.raises(SystemExit):
        pair._build_parser().parse_args(
            ["--dry-run-timing", "--trigger-out-2-rising-delay-us", value])


def test_pair_runtime_parser_rejects_removed_trigger_delay_fraction_flag():
    from dmdcontrol.runtime import pair

    with pytest.raises(SystemExit):
        pair._build_parser().parse_args(
            ["--dry-run-timing", "--trigger-out-2-delay-fraction", "0.05"])


def test_pair_runtime_parser_rejects_removed_hz_flag():
    from dmdcontrol.runtime import pair

    with pytest.raises(SystemExit):
        pair._build_parser().parse_args(["--dry-run-timing", "--hz", "120"])


def test_pair_runtime_parser_accepts_generic_exposure_us():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        ["--dry-run-timing", "--test", "dot", "--exposure-us", "4000"])

    assert args.exposure_us == 4000


def test_pair_runtime_parser_accepts_static_images_options():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args([
        "--dry-run-timing",
        "--test",
        STATIC_IMAGES_PAIR_TEST,
        "--static-image-a",
        "images/T.png",
        "--static-image-b",
        "images/O.png",
        "--static-image-size-px",
        "777",
    ])

    assert args.test == STATIC_IMAGES_PAIR_TEST
    assert args.static_image_a == "images/T.png"
    assert args.static_image_b == "images/O.png"
    assert args.static_image_size_px == 777


def test_pair_runtime_rejects_negative_dark_time():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(["--dry-run-timing", "--dark-time-us", "-1"])

    with pytest.raises(SystemExit, match="--dark-time-us must be non-negative"):
        pair._validate_pair_args(args)


def test_pair_runtime_warns_that_dark_time_is_unreliable_in_video_pattern_mode(caplog):
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(["--dry-run-timing", "--dark-time-us", "100"])

    pair._warn_dark_time_video_pattern_mode(args)

    assert "--dark-time-us" in caplog.text
    assert "does not work as expected with DLPC900 Video Pattern Mode" in caplog.text


@pytest.mark.parametrize(
    "flag",
    ["--kernel-exposure-us", "--numbers-exposure-us", "--count-exposure-us"],
)
def test_pair_runtime_parser_rejects_removed_exposure_flags(flag):
    from dmdcontrol.runtime import pair

    with pytest.raises(SystemExit):
        pair._build_parser().parse_args(["--dry-run-timing", flag, "4000"])


def test_lut_override_a_numbers_b_static_returns_digit_count():
    # Test with explicitly provided exposure
    args_1 = types.SimpleNamespace(
        test=A_NUMBERS_B_STATIC_PAIR_TEST,
        numbers=[1,
                 2,
                 3,
                 4,
                 5],
        exposure_us=3000,
    )
    entries_count_1, exposure_1 = _lut_override(args_1, target_hz=60)
    assert entries_count_1 == 5
    assert exposure_1 == 3000

    # Test with 3 numbers and auto-computed exposure (None)
    args_2 = types.SimpleNamespace(
        test=A_NUMBERS_B_STATIC_PAIR_TEST,
        numbers=[1,
                 2,
                 3],
        exposure_us=None,
    )
    entries_count_2, exposure_2 = _lut_override(args_2, target_hz=60)
    assert entries_count_2 == 3
    assert exposure_2 is None


def test_lut_override_a_count_b_static_returns_count_slots():
    args = types.SimpleNamespace(
        test=A_COUNT_B_STATIC_PAIR_TEST,
        count_slots_per_frame=2,
        count_blank_between_frames=False,
        exposure_us=7000,
    )

    entries_count, exposure = _lut_override(args, target_hz=60)

    assert entries_count == 2
    assert exposure == 7000


def test_lut_override_a_count_b_static_doubles_slots_for_blank_bitplanes():
    args = types.SimpleNamespace(
        test=A_COUNT_B_STATIC_PAIR_TEST,
        count_slots_per_frame=2,
        count_blank_between_frames=True,
        exposure_us=4000,
    )

    entries_count, exposure = _lut_override(args, target_hz=60)

    assert entries_count == 4
    assert exposure == 4000


def test_lut_override_non_numbers_test_delegates_to_kernel():
    args = types.SimpleNamespace(
        test="some-other-test",
        numbers=[1,
                 2,
                 3,
                 4,
                 5],
        exposure_us=3000,
        b_exposure_us=None,
        kernel_pairs=5,
        seq_utilization=0.90,
        dark_time_us=None,
    )
    entries_count, exposure = _lut_override(args, target_hz=60)
    # The kernel override should return (None, None) when not enabled, which the runtime treats as default BITPLANES (24)
    assert entries_count is None
    assert exposure == 3000


def test_pair_runtime_parser_accepts_count_mode_options():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--test-b",
            "dot",
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--count-slots-per-frame",
            "2",
            "--count-blank-between-frames",
            "--exposure-us",
            "7000",
        ])

    assert args.count_start == 1
    assert args.count_end == 100
    assert args.count_slots_per_frame == 2
    assert args.count_blank_between_frames is True
    assert args.exposure_us == 7000


def test_pair_runtime_parser_accepts_paired_startup_leader_vsyncs():
    from dmdcontrol.runtime import pair

    default_args = pair._build_parser().parse_args(["--dry-run-timing"])
    explicit_args = pair._build_parser().parse_args(
        ["--dry-run-timing", "--paired-startup-leader-vsyncs", "12"])

    assert default_args.paired_startup_leader_vsyncs == 16
    assert explicit_args.paired_startup_leader_vsyncs == 12


def test_pair_runtime_parser_rejects_negative_paired_startup_leader_vsyncs():
    from dmdcontrol.runtime import pair

    with pytest.raises(SystemExit):
        pair._build_parser().parse_args(
            ["--dry-run-timing", "--paired-startup-leader-vsyncs", "-1"])


def test_startup_leader_metadata_uses_requested_vsync_count():
    from dmdcontrol.runtime import pair

    metadata = pair._startup_leader_metadata(
        {
            "entries_count": 2,
            "trig2_mode": "per_bitplane",
        },
        vsyncs=12,
    )

    assert metadata == {
        "vsyncs": 12,
        "trigger_count": 24,
        "entries_count": 2,
        "trig2_mode": "per_bitplane",
        "frame_role": "blank_startup_leader",
    }


def test_pair_runtime_auto_count_slots_uses_fastest_valid_timing():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "1000",
        ])

    pair._validate_pair_args(args)

    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"


def test_pair_runtime_auto_count_slots_accounts_for_blank_bitplanes():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--count-start",
            "1",
            "--count-end",
            "60",
            "--exposure-us",
            "4000",
            "--seq-utilization",
            "1.0",
            "--count-blank-between-frames",
        ])

    pair._validate_pair_args(args)

    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"
    assert _lut_override(args, target_hz=60) == (4, 4000)


def test_pair_runtime_count_slots_accepts_auto_literal():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--count-slots-per-frame",
            "auto",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "1000",
        ])

    pair._validate_pair_args(args)

    assert args.count_slots_per_frame == 2
    assert args.count_slots_per_frame_mode == "auto"


def test_pair_runtime_explicit_count_slots_override_is_preserved():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--count-start",
            "1",
            "--count-end",
            "100",
            "--count-slots-per-frame",
            "5",
            "--exposure-us",
            "2500",
            "--dark-time-us",
            "250",
        ])

    pair._validate_pair_args(args)

    assert args.count_slots_per_frame == 5
    assert args.count_slots_per_frame_mode == "explicit"


def test_pair_runtime_rejects_count_sequences_that_repeat_before_vsync():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--count-start",
            "1",
            "--count-end",
            "60",
            "--count-slots-per-frame",
            "1",
            "--exposure-us",
            "4000",
            "--seq-utilization",
            "1.0",
            "--count-blank-between-frames",
        ])

    with pytest.raises(SystemExit, match="use --count-slots-per-frame 2"):
        pair._validate_pair_args(args)


def test_pair_runtime_auto_count_slots_rejects_ranges_without_valid_divisor():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_COUNT_B_STATIC_PAIR_TEST,
            "--count-start",
            "1",
            "--count-end",
            "99",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "1000",
        ])

    with pytest.raises(SystemExit, match="No valid --count-slots-per-frame"):
        pair._validate_pair_args(args)


def test_pair_runtime_parser_accepts_numbers_bitplane_order():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            A_NUMBERS_B_STATIC_PAIR_TEST,
            "--numbers",
            "1,2,3,4,5",
            "--numbers-bitplane-order",
            "1,2,3,4,0",
        ])

    assert args.numbers == [1, 2, 3, 4, 5]
    assert args.numbers_bitplane_order == [1, 2, 3, 4, 0]


def test_pair_runtime_parser_accepts_static_dot_radius():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            "dot",
            "--dot-radius",
            "17",
        ])

    assert args.dot_radius == 17


def test_static_dot_dry_run_uses_generic_exposure_for_dynamic_entry_count(monkeypatch):
    from dmdcontrol.runtime import pair

    captured = {}

    def fake_build_lut_entries(*args, **kwargs):
        captured["entries_count"] = kwargs["entries_count"]
        captured["per_entry_exposure_us"] = kwargs["per_entry_exposure_us"]
        captured["dark_time_us"] = kwargs["dark_time_us"]
        return [object(), object(), object()], {
            "entries_count": 3,
            "trig2_mode": "per_bitplane",
            "effective_frame_hz": 60.0,
            "effective_binary_rate_hz": 180.0,
            "exposure_us": 4000,
            "dark_us": 250,
            "total_sequence_us": 12750.0,
            "usable_frame_period_us": 14750.0,
        }

    monkeypatch.setattr(pair, "build_lut_entries", fake_build_lut_entries)

    args = pair._build_parser().parse_args(
        [
            "--dry-run-timing",
            "--test",
            "dot",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "250",
        ])
    pair_config = pair.PairConfig(
        dmd_a=types.SimpleNamespace(xrandr_output="DP-2", usb_id_path="usb-a"),
        dmd_b=types.SimpleNamespace(xrandr_output="DP-0", usb_id_path="usb-b"),
        target_hz=60,
    )

    pair._dry_run_timing(args, pair_config)

    assert captured == {
        "entries_count": None,
        "per_entry_exposure_us": 4000,
        "dark_time_us": 250,
    }


def test_static_dot_radius_applies_to_both_dmds():
    from dmdcontrol.patterns.paired import make_pair_frame_provider

    provider = make_pair_frame_provider("dot", width=21, height=21, dot_radius=3)

    frame_a, frame_b = provider.initial_pair()

    assert frame_a[10, 10, 0] == 255
    assert frame_a[10, 13, 0] == 255
    assert frame_a[10, 14, 0] == 0
    assert np.array_equal(frame_a, frame_b)


@pytest.mark.parametrize(
    ("argv",
     "message"),
    [
        (
            ["--test",
             A_COUNT_B_STATIC_PAIR_TEST,
             "--count-start",
             "5",
             "--count-end",
             "4"],
            "--count-start must be <= --count-end"),
        (
            ["--test",
             A_COUNT_B_STATIC_PAIR_TEST,
             "--test-a",
             "dot"],
            "--test-a is not valid for a-count-b-static"),
        (
            [
                "--test",
                A_COUNT_B_STATIC_PAIR_TEST,
                "--count-start",
                "1",
                "--count-end",
                "5",
                "--count-slots-per-frame",
                "2"],
            "divisible by --count-slots-per-frame",
        ),
        (
            [
                "--test",
                A_COUNT_B_STATIC_PAIR_TEST,
                "--count-end",
                "130",
                "--count-slots-per-frame",
                "2"],
            "at most 64 VSYNC frames",
        ),
    ],
)
def test_pair_runtime_validates_count_mode_options(argv, message):
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(argv)

    with pytest.raises(SystemExit, match=message):
        pair._validate_pair_args(args)


def test_pair_runtime_parser_rejects_nonpositive_count_slots():
    from dmdcontrol.runtime import pair

    with pytest.raises(SystemExit):
        pair._build_parser().parse_args(
            ["--test", A_COUNT_B_STATIC_PAIR_TEST, "--count-slots-per-frame", "0"])


def test_a_numbers_b_static_runtime_forwards_b_static_geometry(monkeypatch):
    from dmdcontrol.runtime import pair

    captured = {}
    provider = object()

    def fake_make_pair_frame_provider(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return provider

    monkeypatch.setattr(pair, "make_pair_frame_provider", fake_make_pair_frame_provider)

    args = types.SimpleNamespace(
        test=A_NUMBERS_B_STATIC_PAIR_TEST,
        test_b="dot",
        numbers=[1,
                 2,
                 3],
        numbers_size_px=123,
        exposure_us=600,
        b_dot_x=955,
        b_dot_y=535,
        b_dot_radius=12,
        b_dot_shape="circle",
        b_dot_invert=False,
    )

    result = pair._make_runtime_pair_frame_provider(
        args,
        engine=types.SimpleNamespace(window=None),
        target_hz=60)

    assert result is provider
    assert captured["args"] == (A_NUMBERS_B_STATIC_PAIR_TEST, )
    assert captured["kwargs"]["test_b"] == "dot"
    assert captured["kwargs"]["numbers"] == [1, 2, 3]
    assert captured["kwargs"]["numbers_size_px"] == 123
    assert captured["kwargs"]["b_dot_x"] == 955
    assert captured["kwargs"]["b_dot_y"] == 535
    assert captured["kwargs"]["b_dot_radius"] == 12
    assert captured["kwargs"]["b_dot_shape"] == "circle"
    assert captured["kwargs"]["b_dot_invert"] is False


def test_a_count_b_static_runtime_forwards_count_geometry(monkeypatch):
    from dmdcontrol.runtime import pair

    captured = {}
    provider = object()

    def fake_make_pair_frame_provider(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return provider

    monkeypatch.setattr(pair, "make_pair_frame_provider", fake_make_pair_frame_provider)

    args = types.SimpleNamespace(
        test=A_COUNT_B_STATIC_PAIR_TEST,
        test_b="dot",
        count_start=1,
        count_end=100,
        count_slots_per_frame=2,
        count_blank_between_frames=True,
        numbers_size_px=123,
        b_dot_x=955,
        b_dot_y=535,
        b_dot_radius=12,
        b_dot_shape="circle",
        b_dot_invert=False,
    )

    result = pair._make_runtime_pair_frame_provider(
        args,
        engine=types.SimpleNamespace(window=None),
        target_hz=60)

    assert result is provider
    assert captured["args"] == (A_COUNT_B_STATIC_PAIR_TEST, )
    assert captured["kwargs"]["test_b"] == "dot"
    assert captured["kwargs"]["count_start"] == 1
    assert captured["kwargs"]["count_end"] == 100
    assert captured["kwargs"]["count_slots_per_frame"] == 2
    assert captured["kwargs"]["count_blank_between_frames"] is True
    assert captured["kwargs"]["numbers_size_px"] == 123
    assert captured["kwargs"]["b_dot_x"] == 955
    assert captured["kwargs"]["b_dot_y"] == 535
    assert captured["kwargs"]["b_dot_radius"] == 12
    assert captured["kwargs"]["b_dot_shape"] == "circle"
    assert captured["kwargs"]["b_dot_invert"] is False


def test_static_images_runtime_forwards_paths_and_size(monkeypatch):
    from dmdcontrol.runtime import pair

    captured = {}
    provider = object()

    def fake_make_pair_frame_provider(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return provider

    monkeypatch.setattr(pair, "make_pair_frame_provider", fake_make_pair_frame_provider)

    args = types.SimpleNamespace(
        test=STATIC_IMAGES_PAIR_TEST,
        static_image_a="images/T.png",
        static_image_b="images/O.png",
        static_image_size_px=777,
    )

    result = pair._make_runtime_pair_frame_provider(
        args,
        engine=types.SimpleNamespace(window=None),
        target_hz=60)

    assert result is provider
    assert captured["args"] == (STATIC_IMAGES_PAIR_TEST, )
    assert captured["kwargs"]["static_image_a"] == "images/T.png"
    assert captured["kwargs"]["static_image_b"] == "images/O.png"
    assert captured["kwargs"]["static_image_size_px"] == 777


def test_pair_live_preview_metadata_includes_count_mode():
    from dmdcontrol.runtime import pair

    args = types.SimpleNamespace(
        test=A_COUNT_B_STATIC_PAIR_TEST,
        test_a=None,
        test_b="dot",
        count_start=1,
        count_end=100,
        count_slots_per_frame=2,
        count_blank_between_frames=True,
        exposure_us=7000,
    )
    pair_config = types.SimpleNamespace(
        dmd_a=types.SimpleNamespace(xrandr_output="DP-2"),
        dmd_b=types.SimpleNamespace(xrandr_output="DP-0"),
        offset_a=(1920,
                  0),
        offset_b=(0,
                  0),
        target_hz=60,
    )

    metadata = pair._build_live_preview_metadata(args, pair_config, state_a=None, state_b=None)

    assert metadata["count"] == {
        "start": 1,
        "end": 100,
        "slots_per_frame": 2,
        "slots_per_frame_mode": "explicit",
        "blank_between_frames": True,
        "lut_entries_per_frame": 4,
        "exposure_us": 7000,
    }


def test_pair_dry_run_timing_rejects_numbers_sequence_when_dark_time_exceeds_budget():
    with pytest.raises(ValueError, match="need .* usable"):
        main(
            [
                "--dry-run-timing",
                "--test",
                A_NUMBERS_B_STATIC_PAIR_TEST,
                "--numbers",
                "1,2,3,4,5",
                "--exposure-us",
                "2900",
                "--dark-time-us",
                "500",
            ])


def test_run_prepared_pair_starts_render_coordinator_without_post_start_sleep(monkeypatch):
    from dmdcontrol.runtime import pair
    import dmdcontrol.hardware.dlpc900 as dlpc_module
    import dmdcontrol.patterns.paired as paired_module

    calls = {}
    dlpcs = []
    coordinator_frames = {}

    class FakeDLPC:

        def __init__(self, **kwargs):
            self.closed = False
            dlpcs.append(self)

        def start_pattern_display(self, value):
            pass

        def set_display_mode(self, value):
            pass

        def apply_block_lock_workaround(self):
            pass

        def close(self):
            self.closed = True

    class FakeEngine:

        def __init__(self, fps):
            pass

        def cleanup(self):
            pass

    class FakeProvider:

        def initial_pair(self):
            return object(), object()

    class FakeCoordinator:

        def wait_until_ready(self, timeout_s=1.0):
            return True

        def release_semantic_frames(self):
            calls["released"] = True

        def join(self):
            calls["joined"] = True

        def stop(self):
            calls["stopped"] = True

    monkeypatch.setattr(dlpc_module, "DLPC900", FakeDLPC)
    monkeypatch.setattr(paired_module, "PairedPatternEngine", FakeEngine)
    monkeypatch.setattr(pair, "_lut_override", lambda args, target_hz: (None, None))
    monkeypatch.setattr(
        pair,
        "_make_runtime_pair_frame_provider", lambda args, engine, target_hz: FakeProvider())

    def fake_start_pair_render_coordinator(*args, **kwargs):
        startup_leader_pair = kwargs["startup_leader_pair"]
        coordinator_frames["a"] = startup_leader_pair.a.copy()
        coordinator_frames["b"] = startup_leader_pair.b.copy()
        calls["startup_leader_vsyncs"] = kwargs["startup_leader_vsyncs"]
        return FakeCoordinator()

    monkeypatch.setattr(pair, "_start_pair_render_coordinator", fake_start_pair_render_coordinator)
    monkeypatch.setattr(
        pair,
        "prepare_dlpc900_for_video_pattern",
        lambda *args, **kwargs: {
            "entries": [], "timing": {}},
    )
    monkeypatch.setattr(pair, "load_pattern_sequence", lambda dlpc, entries: None)
    monkeypatch.setattr(pair, "_build_live_preview_metadata", lambda *args, **kwargs: {})

    def fake_start_loaded_pattern_sequences(dlpc_a, dlpc_b, post_start_delay_s=0.2, verify=False):
        calls["post_start_delay_s"] = post_start_delay_s
        calls["verify"] = verify

    monkeypatch.setattr(pair, "start_loaded_pattern_sequences", fake_start_loaded_pattern_sequences)

    mapping_a = types.SimpleNamespace(
        xrandr_output="DP-2",
        usb_id_path="usb-a",
        usb_devpath_contains=None,
    )
    mapping_b = types.SimpleNamespace(
        xrandr_output="DP-0",
        usb_id_path="usb-b",
        usb_devpath_contains=None,
    )
    pair_config = pair.PairConfig(dmd_a=mapping_a, dmd_b=mapping_b)
    args = types.SimpleNamespace(
        wake_dp=False,
        preview_url=None,
        preview_fps=1.0,
        dual_pixel=False,
        seq_utilization=0.9,
        trig2_frame_zero=False,
        trigger_out_2_rising_delay_us=-20,
        dark_time_us=None,
        paired_startup_leader_vsyncs=16,
        runtime_seconds=1,
    )

    assert pair._run_prepared_pair(args, pair_config) == 0
    assert calls["post_start_delay_s"] == 0.0
    assert calls["verify"] is False
    assert calls["startup_leader_vsyncs"] == 16
    assert calls["released"] is True
    assert calls["joined"] is True
    assert coordinator_frames["a"].shape == (pair.DMD_HEIGHT, pair.DMD_WIDTH, 3)
    assert coordinator_frames["b"].shape == (pair.DMD_HEIGHT, pair.DMD_WIDTH, 3)
    assert not np.any(coordinator_frames["a"])
    assert not np.any(coordinator_frames["b"])
    assert [dlpc.closed for dlpc in dlpcs] == [True, True]


def test_run_prepared_pair_uses_single_render_coordinator_without_pump_handoff(monkeypatch):
    from dmdcontrol.runtime import pair
    import dmdcontrol.hardware.dlpc900 as dlpc_module
    import dmdcontrol.patterns.paired as paired_module

    calls = []
    before_start_context = {}

    class FakeDLPC:

        def __init__(self, **kwargs):
            pass

        def start_pattern_display(self, value):
            calls.append(("start_pattern_display", value))

        def set_display_mode(self, value):
            pass

        def apply_block_lock_workaround(self):
            pass

        def close(self):
            calls.append("close")

    class FakeEngine:

        def __init__(self, fps):
            self.fps = fps

        def display_pair(self, frame_a, frame_b):
            raise AssertionError("test should use coordinator, not direct render calls")

        def cleanup(self):
            calls.append("cleanup")

    class FakeProvider:

        def initial_pair(self):
            return object(), object()

        def next_pair(self):
            return object(), object()

    class FakeCoordinator:

        def wait_until_ready(self, timeout_s=1.0):
            calls.append("render_ready")
            return True

        def release_semantic_frames(self):
            calls.append("release_semantic")

        def join(self):
            calls.append("render_join")

        def stop(self):
            calls.append("render_stop")

    def fake_start_pair_render_coordinator(*args, **kwargs):
        calls.append(("start_render_coordinator", kwargs["startup_leader_vsyncs"]))
        return FakeCoordinator()

    def fake_before_start(context):
        calls.append("before_start")
        before_start_context.update(context)

    monkeypatch.setattr(dlpc_module, "DLPC900", FakeDLPC)
    monkeypatch.setattr(paired_module, "PairedPatternEngine", FakeEngine)
    monkeypatch.setattr(pair, "_lut_override", lambda args, target_hz: (2, 8000))
    monkeypatch.setattr(
        pair,
        "_make_runtime_pair_frame_provider", lambda args, engine, target_hz: FakeProvider())
    assert not hasattr(pair, "_start_pair_pump")
    assert not hasattr(pair, "_stop_pair_pump")
    monkeypatch.setattr(
        pair,
        "_start_pair_render_coordinator",
        fake_start_pair_render_coordinator,
        raising=False,
    )
    monkeypatch.setattr(
        pair,
        "prepare_dlpc900_for_video_pattern",
        lambda *args, **kwargs: {
            "entries": [],
            "timing": {
                "entries_count": 2,
                "trig2_mode": "per_bitplane",
            },
        },
    )
    monkeypatch.setattr(pair, "load_pattern_sequence", lambda dlpc, entries: None)
    monkeypatch.setattr(pair, "_build_live_preview_metadata", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        pair,
        "start_loaded_pattern_sequences",
        lambda *args, **kwargs: calls.append("sequencers_started"),
    )

    mapping_a = types.SimpleNamespace(
        xrandr_output="DP-2",
        usb_id_path="usb-a",
        usb_devpath_contains=None,
    )
    mapping_b = types.SimpleNamespace(
        xrandr_output="DP-0",
        usb_id_path="usb-b",
        usb_devpath_contains=None,
    )
    pair_config = pair.PairConfig(dmd_a=mapping_a, dmd_b=mapping_b)
    args = types.SimpleNamespace(
        wake_dp=False,
        preview_url=None,
        preview_fps=1.0,
        dual_pixel=False,
        seq_utilization=1.0,
        trig2_frame_zero=False,
        trigger_out_2_rising_delay_us=0,
        dark_time_us=None,
        paired_startup_leader_vsyncs=12,
        runtime_seconds=1,
    )

    assert pair._run_prepared_pair(
        args,
        pair_config,
        before_sequencer_start=fake_before_start,
    ) == 0

    assert ("start_render_coordinator", 12) in calls
    assert calls.index("render_ready") < calls.index("before_start")
    assert calls.index("before_start") < calls.index("sequencers_started")
    assert calls.index("sequencers_started") < calls.index("release_semantic")
    assert calls.index("release_semantic") < calls.index("render_join")
    assert before_start_context["startup_leader"] == {
        "vsyncs": 12,
        "trigger_count": 24,
        "entries_count": 2,
        "trig2_mode": "per_bitplane",
        "frame_role": "blank_startup_leader",
    }


def test_run_pair_render_loop_emits_blank_leader_before_first_semantic_frame():
    from dmdcontrol.runtime import pair

    blank_a = np.zeros((1, 1, 3), dtype=np.uint8)
    blank_b = np.zeros((1, 1, 3), dtype=np.uint8)
    first_a = np.full((1, 1, 3), 3, dtype=np.uint8)
    first_b = np.full((1, 1, 3), 4, dtype=np.uint8)
    second_a = np.full((1, 1, 3), 5, dtype=np.uint8)
    second_b = np.full((1, 1, 3), 6, dtype=np.uint8)
    displayed = []

    class FakeEngine:

        def should_close(self):
            return len(displayed) >= 4

        def display_pair(self, frame_a, frame_b):
            displayed.append((frame_a.copy(), frame_b.copy()))

    class FakeProvider:

        def initial_pair(self):
            return first_a, first_b

        def next_pair(self):
            return second_a, second_b

    args = types.SimpleNamespace(runtime_seconds=0)

    pair._run_pair_render_loop(
        None,
        None,
        FakeEngine(),
        FakeProvider(),
        args,
        startup_leader_vsyncs=2,
        startup_leader_pair=(blank_a, blank_b),
    )

    assert [int(frame_a[0, 0, 0]) for frame_a, _ in displayed] == [0, 0, 3, 5]
