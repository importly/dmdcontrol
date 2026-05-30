import types

import pytest

from dmdcontrol.patterns.paired import A_NUMBERS_B_STATIC_PAIR_TEST
from dmdcontrol.runtime.pair import _lut_override, main


def test_pair_runtime_parser_defaults_trigger_delay_to_zero():
    from dmdcontrol.runtime import pair

    args = pair._build_parser().parse_args(["--dry-run-timing"])

    assert args.trigger_out_2_delay_fraction == 0.0


def test_lut_override_a_numbers_b_static_returns_digit_count():
    # Test with explicitly provided exposure
    args_1 = types.SimpleNamespace(
        test=A_NUMBERS_B_STATIC_PAIR_TEST,
        numbers=[1, 2, 3, 4, 5],
        numbers_exposure_us=3000,
    )
    entries_count_1, exposure_1 = _lut_override(args_1, target_hz=60)
    assert entries_count_1 == 5
    assert exposure_1 == 3000

    # Test with 3 numbers and auto-computed exposure (None)
    args_2 = types.SimpleNamespace(
        test=A_NUMBERS_B_STATIC_PAIR_TEST,
        numbers=[1, 2, 3],
        numbers_exposure_us=None,
    )
    entries_count_2, exposure_2 = _lut_override(args_2, target_hz=60)
    assert entries_count_2 == 3
    assert exposure_2 is None


def test_lut_override_non_numbers_test_delegates_to_kernel():
    args = types.SimpleNamespace(
        test="some-other-test",
        numbers=[1, 2, 3, 4, 5],
        numbers_exposure_us=3000,
        b_exposure_us=None,
        kernel_pairs=5,
        kernel_exposure_us=None,
        seq_utilization=0.90,
    )
    entries_count, exposure = _lut_override(args, target_hz=60)
    # The kernel override should return (None, None) when not enabled, which the runtime treats as default BITPLANES (24)
    assert entries_count is None
    assert exposure is None


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
        numbers=[1, 2, 3],
        numbers_size_px=123,
        numbers_exposure_us=600,
        b_dot_x=955,
        b_dot_y=535,
        b_dot_radius=12,
        b_dot_shape="circle",
        b_dot_invert=False,
    )

    result = pair._make_runtime_pair_frame_provider(args, engine=types.SimpleNamespace(window=None), target_hz=60)

    assert result is provider
    assert captured["args"] == (A_NUMBERS_B_STATIC_PAIR_TEST,)
    assert captured["kwargs"]["test_b"] == "dot"
    assert captured["kwargs"]["numbers"] == [1, 2, 3]
    assert captured["kwargs"]["numbers_size_px"] == 123
    assert captured["kwargs"]["b_dot_x"] == 955
    assert captured["kwargs"]["b_dot_y"] == 535
    assert captured["kwargs"]["b_dot_radius"] == 12
    assert captured["kwargs"]["b_dot_shape"] == "circle"
    assert captured["kwargs"]["b_dot_invert"] is False


def test_pair_dry_run_timing_rejects_numbers_sequence_when_dark_time_exceeds_budget():
    with pytest.raises(ValueError, match="need .* usable"):
        main([
            "--dry-run-timing",
            "--test",
            A_NUMBERS_B_STATIC_PAIR_TEST,
            "--numbers",
            "1,2,3,4,5",
            "--numbers-exposure-us",
            "2900",
            "--dark-time-us",
            "500",
        ])


def test_run_prepared_pair_starts_rendering_without_post_start_sleep(monkeypatch):
    from dmdcontrol.runtime import pair
    import dmdcontrol.hardware.dlpc900 as dlpc_module
    import dmdcontrol.patterns.paired as paired_module

    calls = {}

    class FakeDLPC:
        def __init__(self, **kwargs):
            pass

        def start_pattern_display(self, value):
            pass

        def set_display_mode(self, value):
            pass

        def apply_block_lock_workaround(self):
            pass

    class FakeEngine:
        def __init__(self, fps):
            pass

        def display_pair(self, frame_a, frame_b):
            pass

        def cleanup(self):
            pass

    class FakeProvider:
        def initial_pair(self):
            return object(), object()

    monkeypatch.setattr(dlpc_module, "DLPC900", FakeDLPC)
    monkeypatch.setattr(paired_module, "PairedPatternEngine", FakeEngine)
    monkeypatch.setattr(pair, "_lut_override", lambda args, target_hz: (None, None))
    monkeypatch.setattr(pair, "_make_runtime_pair_frame_provider", lambda args, engine, target_hz: FakeProvider())
    monkeypatch.setattr(pair, "_start_pair_pump", lambda engine, provider: (object(), object()))
    monkeypatch.setattr(pair, "_stop_pair_pump", lambda engine, pump_event, pump_thread: None)
    monkeypatch.setattr(
        pair,
        "prepare_dlpc900_for_video_pattern",
        lambda *args, **kwargs: {"entries": [], "timing": {}},
    )
    monkeypatch.setattr(pair, "load_pattern_sequence", lambda dlpc, entries: None)
    monkeypatch.setattr(pair, "_build_live_preview_metadata", lambda *args, **kwargs: {})
    monkeypatch.setattr(pair, "_run_pair_render_loop", lambda *args, **kwargs: None)

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
        trigger_out_2_delay_fraction=0.03,
        dark_time_us=None,
    )

    assert pair._run_prepared_pair(args, pair_config) == 0
    assert calls == {"post_start_delay_s": 0.0, "verify": True}
