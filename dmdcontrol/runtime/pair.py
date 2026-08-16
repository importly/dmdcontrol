"""Paired dual-DMD runtime for one 3840x1080 OpenGL swap loop."""

from __future__ import annotations

import time
import logging
import numpy as np
from concurrent.futures import ThreadPoolExecutor

from dmdcontrol.dmd import DLPC900, load_from_config
from dmdcontrol.patterns import PairedPatternEngine
from dmdcontrol.runtime import (
    PairRenderCoordinator,
    _blank_pair_frames,
    _start_pair_render_coordinator,
    build_dynamic_fm_sequence,
    prepare_dlpc900_for_video_pattern,
    load_pattern_sequence,
    start_loaded_pattern_sequences
)
from dmdcontrol.utils import CONFIG

logger = logging.getLogger(__name__)


def _prepare_pair_controllers(
    dlpc_a,
    dlpc_b,
    *,
    timing_a,
    timing_b,
    entries_count_a: int,
    entries_count_b: int,
) -> None:
    def prepare(label, dlpc, timing, entries_count):
        logger.info('Preparing controller without starting sequencer...')
        prepare_dlpc900_for_video_pattern(dlpc, entries_count=entries_count)
        logger.info('Controller preparation complete.')

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="dlpc900-prepare") as executor:
        futures = (
            executor.submit(prepare, "A", dlpc_a, timing_a, entries_count_a),
            executor.submit(prepare, "B", dlpc_b, timing_b, entries_count_b),
        )
        for future in futures:
            future.result()


def main(fm: np.ndarray, k: np.ndarray) -> int:
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
    try:
        engine = PairedPatternEngine()
        sequence = build_dynamic_fm_sequence(
            fm,
            k,
        )

        plan_a = sequence.lut_plan_a()
        plan_b = sequence.lut_plan_for_b()
        lut_entries_a = list(plan_a.entries)
        lut_entries_b = list(plan_b.entries)

        if CONFIG.get('DMD', {}).get('wake_dp', False):
            for dlpc in (dlpc_a, dlpc_b):
                logger.info('Waking DisplayPort receiver for DMD %s.', dlpc.dmd.name)
                dlpc.wake_displayport_receiver()
            time.sleep(1.0)

        prime_first_semantic = sequence.startup_policy.mode == "prime_first_frame"
        startup_leader_pair = sequence.startup_pair or _blank_pair_frames()
        startup_leader_vsyncs = int(sequence.startup_policy.leader_vsyncs)
        logger.info('Starting paired continuous GL render coordinator with configured startup frames...')
        render_coordinator = _start_pair_render_coordinator(
            engine,
            provider,
            startup_leader_pair=startup_leader_pair,
            startup_leader_vsyncs=startup_leader_vsyncs,
        )
        if not render_coordinator.wait_until_ready(timeout_s=1.0):
            raise RuntimeError('Paired render coordinator did not become ready.')

        logger.info('Preparing both DLPC900 controllers concurrently...')
        _prepare_pair_controllers(
            dlpc_a,
            dlpc_b,
            timing_a=plan_a.timing,
            timing_b=plan_b.timing,
            entries_count_a=len(lut_entries_a),
            entries_count_b=len(lut_entries_b),
        )

        logger.info('Loading paired pattern LUTs without starting sequencers...')
        load_pattern_sequence(dlpc_a, lut_entries_a)
        load_pattern_sequence(dlpc_b, lut_entries_b)

        if prime_first_semantic:
            logger.info('Priming first count/blank source frame before sequencer start...')
            if not render_coordinator.prime_first_semantic_frame(timeout_s=1.0):
                raise RuntimeError('Timed out priming first count/blank source frame before sequencer start.')

        logger.info('Starting both DLPC900 sequencers from paired software barrier...')
        # Keep the startup-critical path short: HID readback verification can add
        # an unpredictable delay after one controller starts. The live GL thread
        # is already showing blanks, so we start both sequencers, release the
        # fixed blank leader, and then advance to provider.initial_pair().
        start_loaded_pattern_sequences(
            dlpc_a, dlpc_b, post_start_delay_s=0.0, verify=False
        )
        logger.info('[SCOPE] Compare TRIG_OUT_2_A and TRIG_OUT_2_B for start skew and drift.')
        render_coordinator.release_semantic_frames()
        render_coordinator.join()
        render_coordinator = None
        return 0
    finally:
        if render_coordinator is not None:
            render_coordinator.stop()
        for _, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            if dlpc is None:
                continue
            try:
                logger.info('Stopping pattern display...')
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
