import types

import numpy as np

from dmdcontrol.patterns.bitplanes import extract_bitplane
from dmdcontrol.patterns.modes import generate_decimal_number_rgb
from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    as_frame_pair,
)
from dmdcontrol.runtime import display_sequence
from dmdcontrol.runtime.lifecycle import LutEntry


def _assert_sequence_cursor(sequence):
    assert type(sequence.provider).__name__ == "FrameSequenceProvider"


def _count_args(**overrides):
    defaults = {
        "test": A_COUNT_B_STATIC_PAIR_TEST,
        "test_a": None,
        "test_b": "dot",
        "count_start": 1,
        "count_end": 4,
        "count_slots_per_frame": 1,
        "count_slots_per_frame_mode": "explicit",
        "count_blank_between_frames": True,
        "numbers_size_px": 80,
        "b_dot_x": 60,
        "b_dot_y": 80,
        "b_dot_radius": 3,
        "b_dot_shape": "circle",
        "b_dot_invert": False,
        "dot_radius": 3,
        "static_image_a": None,
        "static_image_b": None,
        "static_image_size_px": 160,
        "kernel_px": 30,
        "kernel_leader_frames": 3,
        "kernel_blank_end_frame": True,
        "kernel_single_shot": False,
        "a_calibr_square_control_file": None,
        "exposure_us": 8000,
        "dark_time_us": None,
        "seq_utilization": 1.0,
        "trig2_frame_zero": False,
        "paired_startup_leader_vsyncs": 16,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def test_count_blank_sequence_pairs_each_frame_with_its_lut_slots():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert sequence.startup_policy.mode == "prime_first_frame"
    assert sequence.startup_leader_metadata()["trigger_count"] == 1
    assert sequence.lut_entries() == [
        LutEntry(0, 8000, False, 1, 7, 0, False, 0),
        LutEntry(1, 8000, True, 1, 7, 0, False, 1),
    ]
    assert sequence.expected_trigger_count() == 8
    assert sequence.timing["entries_count"] == 2

    frame0 = sequence.frames[0]
    assert [slot.semantic_label for slot in frame0.lut_slots] == ["blank", "count:1"]
    assert int(np.count_nonzero(extract_bitplane(frame0.frame_pair.a, 0))) == 0
    np.testing.assert_array_equal(
        extract_bitplane(frame0.frame_pair.a, 1),
        generate_decimal_number_rgb(1, width=120, height=160, size_px=80)[:, :, 0],
    )


def test_count_blank_sequence_keeps_changing_count_out_of_first_vsync_slot():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    frame0 = sequence.frames[0]
    assert [slot.semantic_label for slot in frame0.lut_slots] == ["blank", "count:1"]
    assert int(np.count_nonzero(extract_bitplane(frame0.frame_pair.a, 0))) == 0
    np.testing.assert_array_equal(
        extract_bitplane(frame0.frame_pair.a, 1),
        generate_decimal_number_rgb(1, width=120, height=160, size_px=80)[:, :, 0],
    )
    assert sequence.startup_leader_metadata()["phase_guard_trigger_count"] == 1


def test_exact_count_blank_sixty_sequence_keeps_frames_luts_and_provider_in_order():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(count_end=60),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert len(sequence.frames) == 60
    assert sequence.startup_policy.mode == "prime_first_frame"
    assert sequence.startup_leader_metadata()["trigger_count"] == 1
    assert sequence.lut_entries() == [
        LutEntry(0, 8000, False, 1, 7, 0, False, 0),
        LutEntry(1, 8000, True, 1, 7, 0, False, 1),
    ]
    assert sequence.expected_trigger_count() == 120

    for index, frame in enumerate(sequence.frames):
        count = index + 1
        assert frame.source_frame_index == index
        assert frame.semantic_labels == (f"count:{count}",)
        assert [slot.semantic_label for slot in frame.lut_slots] == ["blank", f"count:{count}"]
        assert [slot.semantic_role for slot in frame.lut_slots] == ["blank", "count"]
        assert [slot.bitplane_index for slot in frame.lut_slots] == [0, 1]
        assert [slot.exposure_us for slot in frame.lut_slots] == [8000, 8000]
        assert [slot.trig2_enabled for slot in frame.lut_slots] == [True, True]
        assert int(np.count_nonzero(extract_bitplane(frame.frame_pair.a, 0))) == 0
        np.testing.assert_array_equal(
            extract_bitplane(frame.frame_pair.a, 1),
            generate_decimal_number_rgb(count, width=120, height=160, size_px=80)[:, :, 0],
        )

    runtime_first = as_frame_pair(sequence.provider.initial_pair())
    runtime_second = as_frame_pair(sequence.provider.next_pair())
    _assert_sequence_cursor(sequence)
    np.testing.assert_array_equal(runtime_first.a, sequence.frames[0].frame_pair.a)
    np.testing.assert_array_equal(runtime_second.a, sequence.frames[1].frame_pair.a)
    np.testing.assert_array_equal(runtime_first.b, runtime_second.b)


def test_count_without_blank_sequence_uses_blank_leader_policy():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(count_blank_between_frames=False, exposure_us=16000),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert sequence.startup_policy.mode == "blank_leader"
    assert sequence.startup_policy.leader_vsyncs == 16
    assert sequence.startup_leader_metadata()["trigger_count"] == 16
    assert sequence.lut_entries() == [LutEntry(0, 16000, True, 1, 7, 0, False, 0)]


def test_removed_numbers_sequence_mode_is_rejected():
    with np.testing.assert_raises(ValueError):
        display_sequence.build_paired_display_sequence(
            _count_args(
                test="a-numbers-b-static",
                count_blank_between_frames=False,
                exposure_us=3000,
            ),
            target_hz=60,
            engine=types.SimpleNamespace(window=None),
            width=120,
            height=160,
        )


def test_static_sequence_has_one_repeating_frame_and_timing_from_exposure():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(test="checkerboard", exposure_us=4000),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert len(sequence.frames) == 1
    assert sequence.repeat is True
    np.testing.assert_array_equal(
        as_frame_pair(sequence.provider.initial_pair()).a,
        sequence.frames[0].frame_pair.a,
    )
    np.testing.assert_array_equal(
        as_frame_pair(sequence.provider.next_pair()).a,
        sequence.frames[0].frame_pair.a,
    )
    assert sequence.lut_slots[0].exposure_us == 4000


def test_kernel_sequence_preserves_kernel_cycle_metadata_and_uses_sequence_cursor():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(
            test=KERNEL_STATIC_PAIR_TEST,
            test_b="dot",
            exposure_us=3000,
            kernel_px=30,
            kernel_leader_frames=3,
            kernel_blank_end_frame=True,
            kernel_single_shot=False,
        ),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert sequence.mode_metadata["kernel"]["kernel_px"] == 30
    assert sequence.mode_metadata["kernel"]["cycle_fires"] >= 512
    _assert_sequence_cursor(sequence)
    runtime_first = as_frame_pair(sequence.provider.initial_pair())
    runtime_second = as_frame_pair(sequence.provider.next_pair())
    np.testing.assert_array_equal(runtime_first.a, sequence.frames[0].frame_pair.a)
    np.testing.assert_array_equal(runtime_second.a, sequence.frames[1].frame_pair.a)
    assert sequence.lut_slots[0].exposure_us == 3000


def test_calibration_dot_sequence_uses_dynamic_provider_with_common_lut_slots():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(
            test=CALIBRATION_DOT_PAIR_TEST,
            exposure_us=4000,
            a_calibr_square_control_file=None,
        ),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert sequence.startup_policy.mode == "blank_leader"
    assert sequence.provider is not None
    assert type(sequence.provider).__name__ != "FrameSequenceProvider"
    assert sequence.lut_slots[0].exposure_us == 4000
