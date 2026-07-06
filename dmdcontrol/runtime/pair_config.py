"""Paired DMD mapping and layout configuration."""

from __future__ import annotations

from dataclasses import dataclass

from dmdcontrol.hardware.mapping import DmdMapping, resolve_dmd_mapping
from dmdcontrol.patterns.paired import OFFSET_A, OFFSET_B, PAIR_HEIGHT, PAIR_WIDTH
from dmdcontrol.support.constants import DEFAULT_HZ


@dataclass(frozen=True)
class PairConfig:
    dmd_a: DmdMapping
    dmd_b: DmdMapping
    desktop_width: int = PAIR_WIDTH
    desktop_height: int = PAIR_HEIGHT
    offset_b: tuple[int, int] = OFFSET_B
    offset_a: tuple[int, int] = OFFSET_A
    target_hz: int = DEFAULT_HZ


def resolve_pair_config(config_path: str | None = None) -> PairConfig:
    dmd_a = resolve_dmd_mapping("A", config_path)
    dmd_b = resolve_dmd_mapping("B", config_path)
    for mapping in (dmd_a, dmd_b):
        if not mapping.xrandr_output:
            raise ValueError(f"DMD {mapping.name} must define xrandr_output for paired runs.")
        if not mapping.usb_id_path:
            raise ValueError(f"DMD {mapping.name} must define usb_id_path for paired runs.")

    return PairConfig(dmd_a=dmd_a, dmd_b=dmd_b)
