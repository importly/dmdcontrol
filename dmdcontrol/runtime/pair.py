"""Paired dual-DMD runtime for one 3840x1080 OpenGL swap loop."""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from typing import TypedDict

from dmdcontrol.hardware.mapping import DmdMapping
from dmdcontrol.preview.render import LivePreviewPoster
from dmdcontrol.runtime.display_sequence import (
    DisplaySequenceMetadata,
    StartupLeaderMetadata,
    build_paired_display_sequence,
)
from dmdcontrol.runtime.lifecycle import (
    PreparedSequenceState,
    load_pattern_sequence,
    prepare_dlpc900_for_video_pattern,
    start_loaded_pattern_sequences,
)
from dmdcontrol.runtime.lifecycle import (
    warn_dark_time_video_pattern_mode as _warn_dark_time_video_pattern_mode,
)
from dmdcontrol.runtime.pair_args import (
    _build_parser,
    _is_count_recipe,
    _resolve_count_recipe_args,
    _validate_count_recipe_args,
    _validate_pair_args,
)
from dmdcontrol.runtime.pair_config import PairConfig, resolve_pair_config
from dmdcontrol.runtime.pair_render import (
    PairRenderCoordinator,
    _blank_dmd_frame,
    _blank_pair_frames,
    _display_frame_pair,
    _start_pair_render_coordinator,
)
from dmdcontrol.runtime.pair_reporting import (
    _build_live_preview_metadata,
    _live_preview_metadata_for_frame,
    _metadata_int,
)
from dmdcontrol.support.constants import DMD_HEIGHT, DMD_WIDTH
from dmdcontrol.support.logging import logger, setup_logger

__all__ = [
    "BeforeStartCallback",
    "BeforeStartContext",
    "DMD_HEIGHT",
    "DMD_WIDTH",
    "DmdMapping",
    "LivePreviewPoster",
    "PairConfig",
    "PairRenderCoordinator",
    "_blank_dmd_frame",
    "_blank_pair_frames",
    "_build_live_preview_metadata",
    "_build_parser",
    "_display_frame_pair",
    "_is_count_recipe",
    "_live_preview_metadata_for_frame",
    "_metadata_int",
    "_resolve_count_recipe_args",
    "_run",
    "_run_namespace",
    "_run_prepared_pair",
    "_start_pair_render_coordinator",
    "_validate_count_recipe_args",
    "_validate_pair_args",
    "_warn_dark_time_video_pattern_mode",
    "build_paired_display_sequence",
    "load_pattern_sequence",
    "main",
    "prepare_dlpc900_for_video_pattern",
    "resolve_pair_config",
    "run_namespace",
    "run_with_before_start_callback",
    "run_with_before_start_namespace",
    "start_loaded_pattern_sequences",
]


class BeforeStartContext(TypedDict):
    args: argparse.Namespace
    pair_config: PairConfig
    state_a: PreparedSequenceState
    state_b: PreparedSequenceState
    preview_metadata: dict[str, object]
    startup_leader: StartupLeaderMetadata
    display_sequence: DisplaySequenceMetadata


BeforeStartCallback = Callable[[BeforeStartContext], None]


def _run_prepared_pair(
    args: argparse.Namespace,
    pair_config: PairConfig,
    before_sequencer_start: BeforeStartCallback | None = None,) -> int:
    from dmdcontrol.hardware.dlpc900 import DLPC900
    from dmdcontrol.patterns.paired import PairedPatternEngine

    logger.info(
        f"[+] Paired DMD layout: B {pair_config.dmd_b.xrandr_output} left +0+0, "
        f"A {pair_config.dmd_a.xrandr_output} right +{DMD_WIDTH}+0")
    engine = None
    dlpc_a = None
    dlpc_b = None
    render_coordinator: PairRenderCoordinator | None = None
    preview_poster: LivePreviewPoster | None = None
    try:
        engine = PairedPatternEngine(fps=pair_config.target_hz)
        sequence = build_paired_display_sequence(
            args,
            target_hz=pair_config.target_hz,
            engine=engine,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
        )
        provider = sequence.provider
        if provider is None:
            raise RuntimeError("paired display sequence did not provide a frame source")
        lut_entries = sequence.lut_entries()
        lut_entries_count = len(lut_entries)
        lut_per_entry_exposure_us = int(sequence.timing["exposure_us"])
        if args.preview_url:
            preview_poster = LivePreviewPoster(args.preview_url, fps=args.preview_fps)
        dlpc_a = DLPC900(
            usb_id_path=pair_config.dmd_a.usb_id_path,
            usb_devpath_contains=pair_config.dmd_a.usb_devpath_contains,
        )
        dlpc_b = DLPC900(
            usb_id_path=pair_config.dmd_b.usb_id_path,
            usb_devpath_contains=pair_config.dmd_b.usb_devpath_contains,
        )

        if args.wake_dp:
            for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
                logger.info(f"[+] Waking DisplayPort receiver for DMD {label}...")
                dlpc.wake_displayport_receiver()
            time.sleep(1.0)

        prime_first_semantic = sequence.startup_policy.mode == "prime_first_frame"
        startup_leader_pair = _blank_pair_frames()
        startup_leader_vsyncs = int(sequence.startup_policy.leader_vsyncs)
        logger.info(
            "[+] Starting paired continuous GL render coordinator with blank pre-start frames...")
        render_coordinator = _start_pair_render_coordinator(
            engine,
            provider,
            args,
            startup_leader_pair=startup_leader_pair,
            startup_leader_vsyncs=startup_leader_vsyncs,
        )
        if not render_coordinator.wait_until_ready(timeout_s=1.0):
            raise RuntimeError("Paired render coordinator did not become ready.")

        logger.info("[+] Preparing DMD A controller without starting sequencer...")
        state_a = prepare_dlpc900_for_video_pattern(
            dlpc_a,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
            entries_count=lut_entries_count,
            per_entry_exposure_us=lut_per_entry_exposure_us,
            trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
            dark_time_us=args.dark_time_us,
        )
        logger.info("[+] Preparing DMD B controller without starting sequencer...")
        state_b = prepare_dlpc900_for_video_pattern(
            dlpc_b,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
            entries_count=lut_entries_count,
            per_entry_exposure_us=lut_per_entry_exposure_us,
            trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
            dark_time_us=args.dark_time_us,
        )

        logger.info("[+] Loading paired pattern LUTs without starting sequencers...")
        load_pattern_sequence(dlpc_a, lut_entries)
        load_pattern_sequence(dlpc_b, lut_entries)
        state_a: PreparedSequenceState = {"entries": lut_entries, "timing": sequence.timing}
        state_b: PreparedSequenceState = {"entries": lut_entries, "timing": sequence.timing}
        live_preview_metadata = _build_live_preview_metadata(
            args,
            pair_config,
            state_a,
            state_b,
            sequence=sequence,
        )
        startup_leader = sequence.startup_leader_metadata()
        live_preview_metadata["startup_leader"] = startup_leader
        render_coordinator.preview_poster = preview_poster
        render_coordinator.preview_metadata = live_preview_metadata

        if before_sequencer_start is not None:
            before_start_context: BeforeStartContext = {
                "args": args,
                "pair_config": pair_config,
                "state_a": state_a,
                "state_b": state_b,
                "preview_metadata": live_preview_metadata,
                "startup_leader": startup_leader,
                "display_sequence": sequence.metadata(),
            }
            before_sequencer_start(before_start_context)

        if prime_first_semantic:
            logger.info(
                "[+] Priming first count/blank source frame before sequencer start...")
            if not render_coordinator.prime_first_semantic_frame(timeout_s=1.0):
                raise RuntimeError(
                    "Timed out priming first count/blank source frame before sequencer start.")

        logger.info("[+] Starting both DLPC900 sequencers from paired software barrier...")
        # Keep the startup-critical path short: HID readback verification can add
        # an unpredictable delay after one controller starts. The live GL thread
        # is already showing blanks, so we start both sequencers, release the
        # fixed blank leader, and then advance to provider.initial_pair().
        start_loaded_pattern_sequences(dlpc_a, dlpc_b, post_start_delay_s=0.0, verify=False)
        logger.info("[SCOPE] Compare TRIG_OUT_2_A and TRIG_OUT_2_B for start skew and drift.")
        render_coordinator.release_semantic_frames()
        render_coordinator.join()
        render_coordinator = None
        return 0
    finally:
        if preview_poster is not None:
            preview_poster.close()
        if render_coordinator is not None:
            render_coordinator.stop()
        for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            if dlpc is None:
                continue
            try:
                logger.info(f"[-] Stopping DMD {label} pattern display...")
                dlpc.start_pattern_display(0)
                dlpc.set_display_mode(0x00)
                dlpc.apply_block_lock_workaround()
            except Exception as cleanup_exc:
                logger.warning(f"DMD {label} cleanup warning: {cleanup_exc}")
            close = getattr(dlpc, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as close_exc:
                    logger.warning(f"DMD {label} close warning: {close_exc}")
        if engine is not None:
            engine.cleanup()


def _run_namespace(
    args: argparse.Namespace,
    before_start: BeforeStartCallback | None = None,) -> int:
    setup_logger(verbosity=args.verbose)
    pair_config = resolve_pair_config(args.dmd_config)
    _validate_pair_args(args, target_hz=pair_config.target_hz)
    _warn_dark_time_video_pattern_mode(args)
    return _run_prepared_pair(args, pair_config, before_sequencer_start=before_start)


def _run(argv: list[str] | None, before_start: BeforeStartCallback | None = None) -> int:
    return _run_namespace(_build_parser().parse_args(argv), before_start)


def run_with_before_start_callback(argv: list[str] | None, before_start: BeforeStartCallback) -> int:
    return _run(argv, before_start)


def run_with_before_start_namespace(
    args: argparse.Namespace,
    before_start: BeforeStartCallback,) -> int:
    return _run_namespace(args, before_start)


def run_namespace(args: argparse.Namespace) -> int:
    return _run_namespace(args)


def main(argv: list[str] | None = None) -> int:
    return _run(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception(f"[ERROR] {exc}")
        raise SystemExit(1)
