import types

import numpy as np

from dmdcontrol.patterns.bitplanes import extract_bitplane
from dmdcontrol.patterns.modes import generate_decimal_number_rgb
from dmdcontrol.patterns.paired import (
    A_COUNT_B_STATIC_PAIR_TEST,
    A_NUMBERS_B_STATIC_PAIR_TEST,
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
)
from dmdcontrol.runtime import display_sequence


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
        "numbers": [1, 2, 3, 4, 5],
        "numbers_size_px": 80,
        "numbers_bitplane_order": None,
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
    assert sequence.startup_leader_metadata()["trigger_count"] == 0
    assert sequence.lut_entries() == [
        (0, 8000, False, 1, 7, 0, False, 0),
        (1, 8000, True, 1, 7, 0, False, 1),
    ]
    assert sequence.expected_trigger_count() == 8
    assert sequence.timing["entries_count"] == 2

    frame0 = sequence.frames[0]
    assert [slot.semantic_label for slot in frame0.lut_slots] == ["count:1", "blank"]
    np.testing.assert_array_equal(
        extract_bitplane(frame0.frame_pair.a, 0),
        generate_decimal_number_rgb(1, width=120, height=160, size_px=80)[:, :, 0],
    )
    assert int(np.count_nonzero(extract_bitplane(frame0.frame_pair.a, 1))) == 0


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
    assert sequence.lut_entries() == [(0, 16000, True, 1, 7, 0, False, 0)]


def test_numbers_sequence_uses_one_lut_slot_per_number():
    sequence = display_sequence.build_paired_display_sequence(
        _count_args(
            test=A_NUMBERS_B_STATIC_PAIR_TEST,
            count_blank_between_frames=False,
            exposure_us=3000,
            numbers=[1, 2, 3],
        ),
        target_hz=60,
        engine=types.SimpleNamespace(window=None),
        width=120,
        height=160,
    )

    assert sequence.startup_policy.mode == "blank_leader"
    assert [slot.bitplane_index for slot in sequence.lut_slots] == [0, 1, 2]
    assert sequence.expected_trigger_count() == 3
    assert sequence.mode_metadata["numbers"]["sequence"] == [1, 2, 3]


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
    assert sequence.lut_slots[0].exposure_us == 4000


def test_kernel_sequence_preserves_kernel_cycle_metadata():
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
    assert sequence.lut_slots[0].exposure_us == 4000
