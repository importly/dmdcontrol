import numpy as np
import pytest

from dmdcontrol.patterns.bitplanes import (
    BITPLANE_LABELS,
    BitplaneMask,
    BitplaneStack,
    PackedRgbFrame,
    bitplane_location,
    extract_bitplane,
    pack_bitplanes_rgb,
    unpack_rgb_bitplanes,
)


def test_bitplane_labels_and_locations_describe_dlpc900_grb_packing():
    assert BITPLANE_LABELS[:3] == ("G0", "G1", "G2")
    assert BITPLANE_LABELS[8] == "R0"
    assert BITPLANE_LABELS[16] == "B0"

    assert bitplane_location(0).label == "G0"
    assert bitplane_location(0).rgb_channel == 1
    assert bitplane_location(0).bit == 0
    assert bitplane_location(8).label == "R0"
    assert bitplane_location(8).rgb_channel == 0
    assert bitplane_location(16).label == "B0"
    assert bitplane_location(16).rgb_channel == 2


def test_bitplane_stack_pads_masks_and_packs_to_rgb_frame():
    mask0 = np.array([[1, 0], [0, 1]], dtype=np.uint8)
    mask8 = np.array([[0, 1], [1, 0]], dtype=np.uint8)

    stack = BitplaneStack.from_masks([mask0, mask8], width=2, height=2)
    packed = stack.to_rgb_frame()

    assert isinstance(packed, PackedRgbFrame)
    assert packed.array.shape == (2, 2, 3)
    np.testing.assert_array_equal(extract_bitplane(packed.array, 0), mask0 * 255)
    np.testing.assert_array_equal(extract_bitplane(packed.array, 1), mask8 * 255)
    assert int(np.count_nonzero(extract_bitplane(packed.array, 2))) == 0


def test_bitplane_stack_can_assign_display_slots_to_requested_bitplanes():
    display_slot_0 = np.array([[1, 0], [0, 0]], dtype=np.uint8)
    display_slot_1 = np.array([[0, 1], [0, 0]], dtype=np.uint8)
    display_slot_2 = np.array([[0, 0], [1, 0]], dtype=np.uint8)

    stack = BitplaneStack.from_display_slots(
        [display_slot_0, display_slot_1, display_slot_2],
        bitplane_order=(1, 2, 0),
        width=2,
        height=2,
    )
    packed = stack.to_rgb_frame().array

    np.testing.assert_array_equal(extract_bitplane(packed, 0), display_slot_2 * 255)
    np.testing.assert_array_equal(extract_bitplane(packed, 1), display_slot_0 * 255)
    np.testing.assert_array_equal(extract_bitplane(packed, 2), display_slot_1 * 255)


def test_bitplane_stack_can_interleave_blank_masks_between_display_masks():
    mask_a = np.array([[1, 0], [0, 0]], dtype=np.uint8)
    mask_b = np.array([[0, 1], [0, 0]], dtype=np.uint8)

    stack = BitplaneStack.from_masks_with_optional_blanks(
        [mask_a, mask_b],
        width=2,
        height=2,
        blank_between_masks=True,
    )
    packed = stack.to_rgb_frame().array

    np.testing.assert_array_equal(extract_bitplane(packed, 0), mask_a * 255)
    assert int(np.count_nonzero(extract_bitplane(packed, 1))) == 0
    np.testing.assert_array_equal(extract_bitplane(packed, 2), mask_b * 255)
    assert int(np.count_nonzero(extract_bitplane(packed, 3))) == 0


def test_bitplane_stack_rejects_invalid_order_and_shapes():
    mask = np.ones((2, 2), dtype=np.uint8)

    with pytest.raises(ValueError, match="bitplane_order length"):
        BitplaneStack.from_display_slots([mask], bitplane_order=(0, 1), width=2, height=2)

    with pytest.raises(ValueError, match="zero-based permutation"):
        BitplaneStack.from_display_slots([mask, mask], bitplane_order=(0, 0), width=2, height=2)

    with pytest.raises(ValueError, match="shape"):
        BitplaneMask.from_array(np.ones((3, 2), dtype=np.uint8), width=2, height=2)


def test_legacy_pack_unpack_wrappers_preserve_behavior():
    masks = [np.zeros((2, 2), dtype=np.uint8) for _ in range(24)]
    masks[0][0, 0] = 1
    masks[8][0, 1] = 1
    masks[16][1, 0] = 1

    packed = pack_bitplanes_rgb(masks, width=2, height=2)
    unpacked = unpack_rgb_bitplanes(packed, width=2, height=2)

    assert packed.dtype == np.uint8
    assert packed.flags["C_CONTIGUOUS"]
    np.testing.assert_array_equal(unpacked[0], masks[0])
    np.testing.assert_array_equal(unpacked[8], masks[8])
    np.testing.assert_array_equal(unpacked[16], masks[16])
