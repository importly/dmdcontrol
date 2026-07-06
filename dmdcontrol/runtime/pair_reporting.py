"""Dry-run and live-preview metadata helpers for paired runtime."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from typing import cast

from dmdcontrol.patterns.paired import (
    CALIBRATION_DOT_PAIR_TEST,
    KERNEL_STATIC_PAIR_TEST,
    STATIC_IMAGES_PAIR_TEST,
    STATIC_PAIR_TESTS,
    PairFrameProvider,
)
from dmdcontrol.preview.render import build_lut_preview_metadata
from dmdcontrol.runtime.count_slots import CountSequenceConfig
from dmdcontrol.runtime.display_sequence import PairedDisplaySequence, build_paired_display_sequence
from dmdcontrol.runtime.lifecycle import (
    LutTimingMetadata,
    PreparedSequenceState,
    compute_trigger_out_2_timing,
)
from dmdcontrol.runtime.pair_args import _is_count_recipe
from dmdcontrol.runtime.pair_config import PairConfig
from dmdcontrol.support.constants import DMD_HEIGHT, DMD_WIDTH
from dmdcontrol.support.logging import logger


def _metadata_int(metadata: Mapping[str, object], key: str, default: int) -> int:
    value = metadata.get(key, default)
    if isinstance(value, (int, float, str)):
        return int(value)
    return default


def _dry_run_timing(args: argparse.Namespace, pair_config: PairConfig) -> int:
    sequence = build_paired_display_sequence(
        args,
        target_hz=pair_config.target_hz,
        engine=None,
        width=DMD_WIDTH,
        height=DMD_HEIGHT,
    )
    entries = sequence.lut_entries()
    timing = cast(LutTimingMetadata, dict(sequence.timing))
    startup_leader = sequence.startup_leader_metadata()
    logger.info(
        f"[DRY RUN] Display sequence: {len(sequence.frames)} source frames, "
        f"{len(sequence.lut_slots)} LUT slots per source frame, "
        f"startup_policy={sequence.startup_policy.mode}, "
        f"startup_leader_triggers={startup_leader['trigger_count']}.")
    logger.info("[DRY RUN] Hardware was not opened. OpenGL and USB modules were not imported.")
    logger.info(
        f"[DRY RUN] X layout: {pair_config.desktop_width}x{pair_config.desktop_height}; "
        f"B {pair_config.dmd_b.xrandr_output} at +{pair_config.offset_b[0]}+{pair_config.offset_b[1]}, "
        f"A {pair_config.dmd_a.xrandr_output} at +{pair_config.offset_a[0]}+{pair_config.offset_a[1]}."
    )
    logger.info(
        f"[DRY RUN] USB: A id_path={pair_config.dmd_a.usb_id_path}, "
        f"B id_path={pair_config.dmd_b.usb_id_path}.")
    if args.test == CALIBRATION_DOT_PAIR_TEST:
        logger.info(
            f"[DRY RUN] Pair content: A=calibr-square control_file="
            f"{args.a_calibr_square_control_file or '(none)'}, "
            f"flicker=every-other-frame, "
            f"B=dot x={args.b_dot_x}, y={args.b_dot_y}, radius={args.b_dot_radius}, "
            f"shape={args.b_dot_shape}, invert={args.b_dot_invert}.")
    elif args.test == KERNEL_STATIC_PAIR_TEST:
        raw_kernel_metadata = sequence.mode_metadata.get("kernel", {})
        kernel_metadata: Mapping[str, object] = (
            raw_kernel_metadata if isinstance(raw_kernel_metadata, Mapping) else {}
        )
        slots = int(timing["entries_count"])
        pad = _metadata_int(kernel_metadata, "pad_fires", (slots - (512 % slots)) % slots)
        payload_vsyncs = _metadata_int(kernel_metadata, "payload_vsyncs", (512 + pad) // slots)
        cycle_vsyncs = _metadata_int(
            kernel_metadata,
            "cycle_vsyncs",
            args.kernel_leader_frames + payload_vsyncs +
            (1 if args.kernel_blank_end_frame else 0),
        )
        logger.info(
            f"[DRY RUN] Pair content: A=kernel kernel_px={args.kernel_px}, "
            f"leader_frames={args.kernel_leader_frames}, blank_end_frame={args.kernel_blank_end_frame}, "
            f"single_shot={args.kernel_single_shot}; B={args.test_b or 'checkerboard'} static.")
        logger.info(
            f"[DRY RUN] A-kernel cycle: {cycle_vsyncs} VSYNC frames, "
            f"{args.kernel_leader_frames * slots} leader fires, 512 kernels, {pad} pad fires"
            f"{', ' + str(slots) + ' end-marker fires' if args.kernel_blank_end_frame else ''}.")
    elif _is_count_recipe(args.test):
        count_config = CountSequenceConfig.from_args(args)
        startup_leader_vsyncs = sequence.startup_policy.leader_vsyncs
        logger.info(
            f"[DRY RUN] Pair content: A=count {args.count_start}..{args.count_end}, "
            f"slots_per_frame={count_config.count_slots_per_frame}, "
            f"blank_after_each_count={count_config.count_blank_between_frames}, "
            f"per-count exposure={args.exposure_us or timing['exposure_us']}us, "
            f"payload_vsyncs={count_config.frame_count}, "
            f"blank_lut_entries_per_vsync={count_config.blank_lut_entries_per_frame}; "
            f"B={args.test_b or 'dot'} static.")
        if sequence.startup_policy.mode == "prime_first_frame":
            logger.info(
                "[DRY RUN] Startup prime: first count/blank source frame is shown "
                "before sequencer start; blank startup leader triggers are disabled "
                f"(effective leader VSYNCs={startup_leader_vsyncs}).")
    elif args.test == STATIC_IMAGES_PAIR_TEST:
        logger.info(
            f"[DRY RUN] Pair content: A=image {args.static_image_a}, "
            f"B=image {args.static_image_b}, size_px={args.static_image_size_px}, "
            f"centered on black {DMD_WIDTH}x{DMD_HEIGHT} canvases.")
    elif args.test in STATIC_PAIR_TESTS:
        logger.info(
            f"[DRY RUN] Pair content: test={args.test}, test_a={args.test_a or args.test}, "
            f"test_b={args.test_b or args.test}, dot_radius={args.dot_radius}.")
    else:
        logger.info(
            f"[DRY RUN] Pair content: dynamic test={args.test}, one shared frame index/timebase.")
    logger.info(
        f"[DRY RUN] Pattern LUT: {len(entries)} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/"
        f"{timing['usable_frame_period_us']:.1f}us usable, "
        f"effective VSYNC={timing['effective_frame_hz']:.3f}Hz.")
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 mode: {timing['trig2_mode']}; expected pulses/s="
        f"{timing['effective_frame_hz'] if args.trig2_frame_zero else timing['effective_binary_rate_hz']:.1f}."
    )
    trigger_timing = compute_trigger_out_2_timing(
        rising_delay_us=args.trigger_out_2_rising_delay_us,
    )
    timing["trigger_out_2"] = trigger_timing
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 rising edge delay={trigger_timing['rising_delay_us']}us, "
        f"falling={trigger_timing['falling_delay_us']}us "
        f"(pulse width {trigger_timing['pulse_width_us']}us).")
    return 0


def _live_preview_metadata_for_frame(
    base_metadata: dict[str, object] | None,
    provider: PairFrameProvider,
) -> dict[str, object]:
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
    sequence: PairedDisplaySequence | None = None,
) -> dict[str, object]:
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
