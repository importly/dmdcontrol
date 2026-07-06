import argparse

import pytest

from dmdcontrol.support.argparse_types import (
    count_slots_per_frame,
    positive_float,
    unit_interval_float,
)
from dmdcontrol.support.constants import (
    DEFAULT_MAX_ACCUMULATION_TRIGGERS,
    DEFAULT_PAIRED_STARTUP_LEADER_VSYNCS,
    DMD_CENTER_X,
    DMD_CENTER_Y,
    DMD_HEIGHT,
    DMD_WIDTH,
    KERNEL_VARIATION_COUNT,
)


def test_display_center_constants_follow_dmd_resolution():
    assert DMD_CENTER_X == DMD_WIDTH // 2
    assert DMD_CENTER_Y == DMD_HEIGHT // 2


def test_capture_defaults_share_kernel_count():
    assert DEFAULT_MAX_ACCUMULATION_TRIGGERS == KERNEL_VARIATION_COUNT
    assert DEFAULT_PAIRED_STARTUP_LEADER_VSYNCS == 16


def test_count_slots_per_frame_accepts_auto_or_positive_integer():
    assert count_slots_per_frame("auto") is None
    assert count_slots_per_frame("3") == 3

    with pytest.raises(argparse.ArgumentTypeError):
        count_slots_per_frame("0")


def test_positive_float_validator():
    assert positive_float("1.25") == 1.25

    with pytest.raises(argparse.ArgumentTypeError):
        positive_float("0")


def test_unit_interval_float_validator():
    assert unit_interval_float("0.5") == 0.5
    assert unit_interval_float("1.0") == 1.0

    with pytest.raises(argparse.ArgumentTypeError):
        unit_interval_float("0")

    with pytest.raises(argparse.ArgumentTypeError):
        unit_interval_float("1.1")
