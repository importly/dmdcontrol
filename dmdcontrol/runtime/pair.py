"""Paired dual-DMD runtime for one 3840x1080 OpenGL swap loop."""

from __future__ import annotations

import time
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict

from dmdcontrol.dmd import DMD, DLPC900, load_from_config
from dmdcontrol.patterns.paired import PairedPatternEngine
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
from dmdcontrol.utils import CONFIG

logger = logging.getLogger(__name__)


class BeforeStartContext(TypedDict):
    args: argparse.Namespace
    pair_config: PairConfig
    state_a: PreparedSequenceState
    state_b: PreparedSequenceState
    preview_metadata: dict[str, object]
    startup_leader: StartupLeaderMetadata
    display_sequence: DisplaySequenceMetadata


BeforeStartCallback = Callable[[BeforeStartContext], None]


def _prepare_pair_controllers(
    dlpc_a,
    dlpc_b,
    *,
    args: argparse.Namespace,
    pair_config: PairConfig,
    timing_a,
    timing_b,
    entries_count_a: int,
    entries_count_b: int,
) -> None:
    def prepare(label, dlpc, timing, entries_count):
        with log_context(f"DMD {label}"):
            logger.info("[+] Preparing controller without starting sequencer...")
            prepare_dlpc900_for_video_pattern(
                dlpc,
                pair_config.target_hz,
                dual_pixel=args.dual_pixel,
                sequence_utilization=timing["sequence_utilization"],
                trig2_frame_zero=timing["trig2_mode"] == "frame_zero",
                entries_count=entries_count,
                per_entry_exposure_us=timing["exposure_us"],
                trigger_out_2_rising_delay_us=args.trigger_out_2_rising_delay_us,
                dark_time_us=timing["dark_us"],
            )
            logger.info("[+] Controller preparation complete.")

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="dlpc900-prepare") as executor:
        futures = (
            executor.submit(prepare, "A", dlpc_a, timing_a, entries_count_a),
            executor.submit(prepare, "B", dlpc_b, timing_b, entries_count_b),
        )
        for future in futures:
            future.result()


def main(
    args: argparse.Namespace,
    *,
    pair_config: PairConfig | None = None,
    before_start: BeforeStartCallback | None = None,
) -> int:
    # Load DMDs from config
    dmds = load_from_config()
    
    # Logging and error checking
    logger.debug('DMDs loaded from config: %s', dmds)
    if len(dmds) != 2:
        logger.error('Expected 2 DMDs in config, found %d', len(dmds))
        raise RuntimeError(f'Expected 2 DMDs in config, found {len(dmds)}')

    # Instantiate controllers
    dlpc_a = DLPC900(dmds[0])
    dlpc_b = DLPC900(dmds[1])
    
    # Logging
    logger.debug("DMD %s instantiated as 'A'.", dmds[0].name)
    logger.debug("DMD %s instantiated as 'B'.", dmds[1].name)
    
    render_coordinator: PairRenderCoordinator | None = None
    preview_poster: LivePreviewPoster | None = None
    try:
        engine = PairedPatternEngine()
        sequence = build_paired_display_sequence(
            args,
            target_hz=pair_config.target_hz,
            engine=engine,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
        )

        plan_a = sequence.lut_plan_a()
        plan_b = sequence.lut_plan_for_b()
        lut_entries_a = list(plan_a.entries)
        lut_entries_b = list(plan_b.entries)

        if CONFIG.wake_dp:
            for dlpc in (dlpc_a, dlpc_b):
                logger.info('Waking DisplayPort receiver for DMD %s.', dlpc.dmd.name)
                dlpc.wake_displayport_receiver()
            time.sleep(1.0)

        prime_first_semantic = sequence.startup_policy.mode == "prime_first_frame"
        startup_leader_pair = sequence.startup_pair or _blank_pair_frames()
        startup_leader_vsyncs = int(sequence.startup_policy.leader_vsyncs)
        logger.info(
            "[+] Starting paired continuous GL render coordinator with configured startup frames..."
        )
        render_coordinator = _start_pair_render_coordinator(
            engine,
            provider,
            args,
            startup_leader_pair=startup_leader_pair,
            startup_leader_vsyncs=startup_leader_vsyncs,
        )
        if not render_coordinator.wait_until_ready(timeout_s=1.0):
            raise RuntimeError("Paired render coordinator did not become ready.")

        logger.info("[+] Preparing both DLPC900 controllers concurrently...")
        _prepare_pair_controllers(
            dlpc_a,
            dlpc_b,
            args=args,
            pair_config=pair_config,
            timing_a=plan_a.timing,
            timing_b=plan_b.timing,
            entries_count_a=len(lut_entries_a),
            entries_count_b=len(lut_entries_b),
        )

        logger.info("[+] Loading paired pattern LUTs without starting sequencers...")
        with log_context("DMD A"):
            load_pattern_sequence(dlpc_a, lut_entries_a)
        with log_context("DMD B"):
            load_pattern_sequence(dlpc_b, lut_entries_b)
        state_a: PreparedSequenceState = {"entries": lut_entries_a, "timing": plan_a.timing}
        state_b: PreparedSequenceState = {"entries": lut_entries_b, "timing": plan_b.timing}

        startup_leader = sequence.startup_leader_metadata()
        render_coordinator.preview_poster = preview_poster
        render_coordinator.preview_metadata = live_preview_metadata

        if before_start is not None:
            before_start_context: BeforeStartContext = {
                "args": args,
                "pair_config": pair_config,
                "state_a": state_a,
                "state_b": state_b,
                "preview_metadata": live_preview_metadata,
                "startup_leader": startup_leader,
                "display_sequence": sequence.metadata(),
            }
            before_start(before_start_context)

        if prime_first_semantic:
            logger.info(
                "[+] Priming first count/blank source frame before sequencer start..."
            )
            if not render_coordinator.prime_first_semantic_frame(timeout_s=1.0):
                raise RuntimeError(
                    "Timed out priming first count/blank source frame before sequencer start."
                )

        logger.info(
            "[+] Starting both DLPC900 sequencers from paired software barrier..."
        )
        # Keep the startup-critical path short: HID readback verification can add
        # an unpredictable delay after one controller starts. The live GL thread
        # is already showing blanks, so we start both sequencers, release the
        # fixed blank leader, and then advance to provider.initial_pair().
        start_loaded_pattern_sequences(
            dlpc_a, dlpc_b, post_start_delay_s=0.0, verify=False
        )
        logger.info(
            "[SCOPE] Compare TRIG_OUT_2_A and TRIG_OUT_2_B for start skew and drift."
        )
        render_coordinator.release_semantic_frames()
        render_coordinator.join()
        render_coordinator = None
        return 0
    finally:
        if render_coordinator is not None:
            render_coordinator.stop()
        for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            if dlpc is None:
                continue
            with log_context(f"DMD {label}"):
                try:
                    logger.info("[-] Stopping pattern display...")
                    dlpc.start_pattern_display(0)
                    dlpc.set_display_mode(0x00)
                    dlpc.apply_block_lock_workaround()
                except Exception as cleanup_exc:
                    logger.exception('Cleanup warning: %s', cleanup_exc)
                close = getattr(dlpc, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as close_exc:
                        logger.exception('Close warning: %s', close_exc)
        if engine is not None:
            engine.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception('%s', exc)
        raise SystemExit(1)
