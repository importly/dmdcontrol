"""Live-preview metadata helpers for paired runtime."""

from __future__ import annotations

import argparse
from collections.abc import Mapping

from dmdcontrol.patterns.paired import PairFrameProvider
from dmdcontrol.preview.render import build_lut_preview_metadata
from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.display_sequence import PairedDisplaySequence
from dmdcontrol.runtime.lifecycle import PreparedSequenceState
from dmdcontrol.runtime.pair_args import _is_count_recipe
from dmdcontrol.runtime.pair_config import PairConfig


def _metadata_int(metadata: Mapping[str, object], key: str, default: int) -> int:
    value = metadata.get(key, default)
    if isinstance(value, (int, float, str)):
        return int(value)
    return default



def _live_preview_metadata_for_frame(
    base_metadata: dict[str, object] | None,
    provider: PairFrameProvider,) -> dict[str, object]:
    metadata = dict(base_metadata or {})
    frame_index = getattr(provider, "frame_index", None)
    if frame_index is not None:
        metadata["source_frame_index"] = int(frame_index)
    return metadata


def _build_live_preview_metadata(
    args: argparse.Namespace,
    pair_config: PairConfig,
    state_a: PreparedSequenceState | None,
    state_b: PreparedSequenceState | None,
    *,
    sequence: PairedDisplaySequence | None = None,) -> dict[str, object]:
    lut_state = state_a or state_b
    metadata = {
        "layout": "pair",
        "test": getattr(args, "test", None),
        "test_a": getattr(args, "test_a", None),
        "test_b": getattr(args, "test_b", None),
        "routes": {
            "B": {
                "position": "left",
                "xrandr_output": pair_config.dmd_b.xrandr_output,
                "offset": list(pair_config.offset_b),
            },
            "A": {
                "position": "right",
                "xrandr_output": pair_config.dmd_a.xrandr_output,
                "offset": list(pair_config.offset_a),
            },
        },
        "target_hz": pair_config.target_hz,
    }
    if sequence is not None:
        metadata.update(sequence.preview_metadata())
        return metadata
    if _is_count_recipe(args.test):
        metadata["count"] = {
            **CountSequenceConfig.from_args(args).to_pair_preview_metadata(),
            "exposure_us": args.exposure_us,
        }
    if lut_state:
        metadata["lut"] = build_lut_preview_metadata(lut_state["entries"], lut_state["timing"])
        metadata["lut_applies_to"] = ["A", "B"]
    return metadata
