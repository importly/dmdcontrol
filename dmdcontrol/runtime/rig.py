"""The paired DMDs, their displays and the camera, brought up once per run.

PairRig.play() shows one sequence and records it: count mode plays once, kernel mode once per
batch (through dmd_conv).
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from functools import partial

import numpy as np

from dmdcontrol.camera import CameraProphsee
from dmdcontrol.dmd import DLPC900, load_from_config
from dmdcontrol.patterns import PairedPatternEngine
from dmdcontrol.utils import CONFIG, WORKSPACE

from .display_sequence import (
    PairedDisplaySequence,
    load_pattern_sequence,
    prepare_pair_controllers,
    start_loaded_pattern_sequences,
    verify_started_pattern_sequence,
)
from .pair_render import _start_pair_render_coordinator

log = logging.getLogger('Rig')

DISPLAY_ID = ':0'


@dataclass
class Capture:
    """One play(): everything recorded, and the trigger of each semantic frame."""

    triggers: np.ndarray
    events: np.ndarray
    semantic: np.ndarray
    dropped: int  # frames the renderer dropped during semantic playback


class PairRig:
    """Context manager: opens both DLPC900s and the camera, wakes the DMDs and sets up the displays."""

    def __enter__(self) -> PairRig:
        dmd_a, dmd_b = load_from_config()
        self.dlpcs = {'A': DLPC900(dmd_a), 'B': DLPC900(dmd_b)}
        self.camera = CameraProphsee()
        try:
            wake_dmds(self.dlpcs)
            setup_displays()
            validate_display()
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_) -> None:
        # play() already stopped the sequencers and restored video mode; stopping again is NACKed
        _cleanup_step('camera close', self.camera.close)
        for name, dlpc in self.dlpcs.items():
            _cleanup_step(f'DMD {name} close', dlpc.close)

    def play(self, sequence: PairedDisplaySequence, cycles: int = 1) -> Capture:
        """Show the startup leader, then cycles x sequence.frames, and record it all."""
        semantic_frames = cycles * len(sequence.frames)
        engine = coordinator = None
        try:
            engine = PairedPatternEngine()
            coordinator = _start_pair_render_coordinator(
                engine,
                sequence.provider,
                startup_leader_pair=sequence.startup_pair,
                startup_leader_vsyncs=sequence.leader_vsyncs,
                semantic_frames=semantic_frames,
            )
            if not coordinator.wait_until_ready(timeout_s=2.0):
                raise RuntimeError('render coordinator did not become ready')

            dlpc_a, dlpc_b = self.dlpcs['A'], self.dlpcs['B']
            prepare_pair_controllers(dlpc_a, dlpc_b)
            load_pattern_sequence(dlpc_a, sequence.entries_a)
            load_pattern_sequence(dlpc_b, sequence.entries_b)
            start_loaded_pattern_sequences(dlpc_a, dlpc_b)
            for name, dlpc in self.dlpcs.items():
                hw = verify_started_pattern_sequence(dlpc, label=f'DMD {name}')
                log.info('DMD %s sequencer running in Video Pattern Mode (hw=%s)',
                         name, f'0x{hw:02X}' if hw is not None else 'n/a')

            nonsemantic_triggers = sequence.leader_triggers + CONFIG.DMD.display_pipeline_vsyncs
            expected_triggers = nonsemantic_triggers + semantic_frames
            log.info('Displaying %d leader + %d semantic frames, expecting %d triggers',
                     sequence.leader_vsyncs, semantic_frames, expected_triggers)

            self.camera.flush()
            coordinator.release_startup_leader()
            coordinator.release_semantic_frames()

            playback_s = semantic_frames / CONFIG.DMD.target_hz

            def _on_record_complete():
                if not coordinator.wait_semantic_frames_done(timeout_s=playback_s + 8.0):
                    raise RuntimeError('semantic playback did not finish')
                coordinator.join()

            # a few extra triggers so a late semantic start still has all its frames
            triggers, events = self.camera.record(expected_triggers + 4, on_complete=_on_record_complete)
            semantic = self.camera.find_semantic_frames(triggers, events, nonsemantic_triggers,
                                                        semantic_frames, search=4)
            dropped = coordinator.semantic_dropped_frames
            log.info('Displayed %d semantic frames, %d dropped', coordinator.semantic_frames_displayed, dropped)
            return Capture(triggers, events, semantic, dropped)
        finally:
            if coordinator is not None:
                _cleanup_step('render coordinator stop', coordinator.stop)
            self._stop_sequencers()
            if engine is not None:
                _cleanup_step('engine cleanup', engine.cleanup)

    def _stop_sequencers(self) -> None:
        for name, dlpc in self.dlpcs.items():
            _cleanup_step(f'DMD {name} stop pattern display', partial(dlpc.start_pattern_display, 0))
            _cleanup_step(f'DMD {name} restore video mode', partial(dlpc.set_display_mode, 0))
            _cleanup_step(f'DMD {name} block-lock workaround', dlpc.apply_block_lock_workaround)


def wake_dmds(dlpcs: dict[str, DLPC900]) -> None:
    for name, dlpc in dlpcs.items():
        log.info('Waking DisplayPort receiver on DMD %s', name)
        dlpc.wake_displayport_receiver()
        time.sleep(1)
        dlpc.set_input_source(0, 1)
        dlpc.set_display_mode(0)
        dlpc.apply_block_lock_workaround()


def setup_displays() -> None:
    script = WORKSPACE / 'scripts' / 'setup_displays.sh'
    log.info('Running display setup: %s', script)
    subprocess.run(['bash', str(script)], check=True)
    os.environ.setdefault('DISPLAY', DISPLAY_ID)


def validate_display() -> None:
    out_a = CONFIG.DMD.A.xrandr_output
    out_b = CONFIG.DMD.B.xrandr_output
    query = subprocess.run(
        ['xrandr', '--display', os.environ.get('DISPLAY', DISPLAY_ID), '--query'],
        capture_output=True, text=True, check=True,
    ).stdout
    problems = []
    if 'current 3840 x 1080' not in query:
        problems.append('screen is not 3840x1080')
    if f'{out_b} connected primary 1920x1080+0+0' not in query:
        problems.append(f'{out_b} (DMD B) is not primary at +0+0')
    if f'{out_a} connected 1920x1080+1920+0' not in query \
            and f'{out_a} connected primary 1920x1080+1920+0' not in query:
        problems.append(f'{out_a} (DMD A) is not at +1920+0')
    if problems:
        raise RuntimeError('display validation failed: ' + '; '.join(problems))
    log.info('Display validated: 3840x1080, %s left (B, primary), %s right (A)', out_b, out_a)


def _cleanup_step(description: str, action) -> None:
    try:
        action()
    except Exception as exc:
        log.warning('Cleanup (%s): %s', description, exc)
