from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from dmdcontrol.support.constants import BITPLANES

BITPLANE_LABELS = tuple(
    [f"G{bit}" for bit in range(8)]
    + [f"R{bit}" for bit in range(8)]
    + [f"B{bit}" for bit in range(8)]
)
_BITPLANE_RGB_CHANNELS = (1,) * 8 + (0,) * 8 + (2,) * 8
_BITPLANE_BITS = tuple(range(8)) * 3

BinaryMaskArray = NDArray[np.uint8]
RGBFrameArray = NDArray[np.uint8]


@dataclass(frozen=True)
class BitplaneLocation:
    index: int
    label: str
    rgb_channel: int
    bit: int


def bitplane_location(index: int) -> BitplaneLocation:
    index = int(index)
    if index < 0 or index >= BITPLANES:
        raise ValueError(f"bitplane index must be in [0, {BITPLANES - 1}]")
    return BitplaneLocation(
        index=index,
        label=BITPLANE_LABELS[index],
        rgb_channel=_BITPLANE_RGB_CHANNELS[index],
        bit=_BITPLANE_BITS[index],
    )


@dataclass(frozen=True)
class BitplaneMask:
    """One validated binary mask for a single DLPC900 bitplane slot."""

    array: BinaryMaskArray

    @property
    def height(self) -> int:
        return int(self.array.shape[0])

    @property
    def width(self) -> int:
        return int(self.array.shape[1])

    @classmethod
    def from_array(
        cls,
        array: object,
        *,
        width: int,
        height: int,
        label: str = "mask",
    ) -> BitplaneMask:
        mask = np.asarray(array)
        if mask.shape != (int(height), int(width)):
            raise ValueError(
                f"{label} must have shape {(int(height), int(width))}, got {mask.shape}"
            )
        return cls(np.ascontiguousarray((mask > 0).astype(np.uint8)))

    @classmethod
    def blank(cls, *, width: int, height: int) -> BitplaneMask:
        return cls(np.zeros((int(height), int(width)), dtype=np.uint8))


@dataclass(frozen=True)
class PackedRgbFrame:
    """One RGB888 frame containing the 24 packed DLPC900 bitplanes."""

    array: RGBFrameArray

    @property
    def height(self) -> int:
        return int(self.array.shape[0])

    @property
    def width(self) -> int:
        return int(self.array.shape[1])

    @classmethod
    def from_array(
        cls,
        array: object,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> PackedRgbFrame:
        frame = np.asarray(array)
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(f"packed RGB frame must have shape HxWx3, got {frame.shape}")
        if width is not None and height is not None and frame.shape[:2] != (int(height), int(width)):
            raise ValueError(
                f"packed RGB frame must be {int(height)}x{int(width)}, got {frame.shape[:2]}"
            )
        if frame.dtype != np.uint8:
            raise ValueError("packed RGB frame must use dtype uint8")
        return cls(np.ascontiguousarray(frame))

    def extract_bitplane(self, index: int) -> BinaryMaskArray:
        location = bitplane_location(index)
        return (
            ((self.array[:, :, location.rgb_channel] >> location.bit) & 1) * 255
        ).astype(np.uint8)

    def unpack_masks(self) -> list[BinaryMaskArray]:
        return [(self.extract_bitplane(index) > 0).astype(np.uint8) for index in range(BITPLANES)]


@dataclass(frozen=True)
class BitplaneStack:
    """A complete 24-slot bitplane stack for one displayed RGB frame."""

    masks: tuple[BitplaneMask, ...]
    width: int
    height: int

    @classmethod
    def from_masks(
        cls,
        masks: Iterable[BitplaneMask | BinaryMaskArray],
        *,
        width: int,
        height: int,
    ) -> BitplaneStack:
        coerced = [
            _coerce_bitplane_mask(mask, width=int(width), height=int(height), label=f"mask {index}")
            for index, mask in enumerate(masks)
        ]
        if len(coerced) > BITPLANES:
            raise ValueError(f"masks can contain at most {BITPLANES} entries")
        blank = BitplaneMask.blank(width=int(width), height=int(height))
        coerced.extend(blank for _ in range(BITPLANES - len(coerced)))
        return cls(tuple(coerced), int(width), int(height))

    @classmethod
    def from_display_slots(
        cls,
        display_masks: Sequence[BitplaneMask | BinaryMaskArray],
        *,
        bitplane_order: Sequence[int],
        width: int,
        height: int,
    ) -> BitplaneStack:
        display_masks = list(display_masks)
        order = tuple(int(index) for index in bitplane_order)
        if len(order) != len(display_masks):
            raise ValueError("bitplane_order length must match display mask count")
        if sorted(order) != list(range(len(display_masks))):
            raise ValueError("bitplane_order must be a zero-based permutation of display slots")

        ordered: list[BitplaneMask | BinaryMaskArray] = list(display_masks)
        for display_slot, bitplane_index in enumerate(order):
            ordered[bitplane_index] = display_masks[display_slot]
        return cls.from_masks(ordered, width=width, height=height)

    @classmethod
    def from_masks_with_optional_blanks(
        cls,
        masks: Iterable[BitplaneMask | BinaryMaskArray],
        *,
        width: int,
        height: int,
        blank_between_masks: bool = False,
    ) -> BitplaneStack:
        masks = list(masks)
        if not blank_between_masks:
            return cls.from_masks(masks, width=width, height=height)

        blank = BitplaneMask.blank(width=int(width), height=int(height))
        interleaved = []
        for mask in masks:
            interleaved.append(mask)
            interleaved.append(blank)
        return cls.from_masks(interleaved, width=width, height=height)

    def to_rgb_frame(self) -> PackedRgbFrame:
        red = np.zeros((self.height, self.width), dtype=np.uint8)
        green = np.zeros((self.height, self.width), dtype=np.uint8)
        blue = np.zeros((self.height, self.width), dtype=np.uint8)
        channels = (red, green, blue)
        for index, mask in enumerate(self.masks):
            location = bitplane_location(index)
            channels[location.rgb_channel][:, :] |= mask.array << location.bit
        return PackedRgbFrame(np.ascontiguousarray(np.stack([red, green, blue], axis=-1)))


def _coerce_bitplane_mask(
    mask: BitplaneMask | BinaryMaskArray,
    *,
    width: int,
    height: int,
    label: str,
) -> BitplaneMask:
    if isinstance(mask, BitplaneMask):
        if mask.array.shape != (height, width):
            raise ValueError(
                f"{label} must have shape {(height, width)}, got {mask.array.shape}"
            )
        return mask
    return BitplaneMask.from_array(mask, width=width, height=height, label=label)


def pack_bitplanes_rgb(
    binary_images: Iterable[BitplaneMask | BinaryMaskArray],
    width: int,
    height: int,
) -> RGBFrameArray:
    binary_images = list(binary_images)
    if len(binary_images) != BITPLANES:
        raise ValueError(f"expected {BITPLANES} binary images, got {len(binary_images)}")
    return BitplaneStack.from_masks(binary_images, width=width, height=height).to_rgb_frame().array


def unpack_rgb_bitplanes(rgb_array: object, width: int, height: int) -> list[BinaryMaskArray]:
    return PackedRgbFrame.from_array(rgb_array, width=width, height=height).unpack_masks()


def extract_bitplane(packed_frame: object, plane: int) -> BinaryMaskArray:
    return PackedRgbFrame.from_array(packed_frame).extract_bitplane(plane)
