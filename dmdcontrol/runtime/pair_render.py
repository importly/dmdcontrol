"""Paired render-thread coordination for startup and semantic playback."""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np

from dmdcontrol.patterns import (
    FramePair,
    PairFrameProvider,
    RGBFrame,
    as_frame_pair,
)
from dmdcontrol.utils import CONFIG

DMD_WIDTH = CONFIG.get('DMD', {}).get('width')
DMD_HEIGHT = CONFIG.get('DMD', {}).get('height')
MAX_RUNTIME_SECONDS = CONFIG.get('Run', {}).get('time_max_s', 9999999)


def _blank_dmd_frame() -> RGBFrame:
    return np.zeros((DMD_HEIGHT, DMD_WIDTH, 3), dtype=np.uint8)


def _blank_pair_frames() -> FramePair:
    return FramePair(a=_blank_dmd_frame(), b=_blank_dmd_frame())


def _display_frame_pair(
    engine: Any,
    frame_pair: FramePair | tuple[RGBFrame, RGBFrame],
) -> None:
    frames = as_frame_pair(frame_pair)
    engine.display_pair(frames.a, frames.b)


class PairRenderCoordinator:
    """Own one GL render thread from configured startup through semantic playback.

    The paired DLPC900 startup path is intentionally staged this way:
    1. Start one GL thread and hold the configured startup pair while USB/DLPC
       setup is still happening. Count/static mode uses A blank and B illuminated;
       other modes may use a blank pair. This keeps the DisplayPort pipeline active
       without advancing the semantic frame provider.
    2. Start both sequencers.
    3. Display a fixed number of configured startup-leader VSYNCs. Those VSYNCs
       create real TRIG_OUT_2 pulses, but they are intentionally non-semantic and
       are recorded in metadata as `startup_leader.trigger_count`.
    4. Only then request provider.initial_pair(), which should be the first real
       displayed frame such as count "1" / dot.

    Camera analysis must skip the startup-leader trigger count before labeling
    trigger windows. Otherwise the first non-semantic leader pulse is mislabeled
    as the first displayed number, shifting the whole sequence.

    those stages are separated by two caller, makes entire thing more explicit

    start()                     -> phase 1: hold startup pair
    release_startup_leader()    -> phase 2: exactly n (16) leader VSYNCs
    wait_leader_done()             (phase 2 complete)
                                -> phase 2b: hold leader pair, should still be triggering 
                                but if its working then thats fine, just waiting for it release semantic frames to be called
    release_semantic_frames()   -> phase 3: semantic playback
    wait_semantic_frames_done()    (phase 3 complete)
    join()                         (thread exited)
    """

    def __init__(
        self,
        engine: Any,
        provider: PairFrameProvider,
        *,
        startup_leader_pair: FramePair | tuple[RGBFrame, RGBFrame],
        startup_leader_vsyncs: int,
        semantic_frames: int,
    ) -> None:
        self.engine = engine
        self.provider = provider
        self.semantic_frames = int(semantic_frames)
        self.startup_leader_pair = as_frame_pair(startup_leader_pair)
        self.startup_leader_vsyncs = int(startup_leader_vsyncs)
        self._ready = threading.Event()
        self._prime_first_semantic = threading.Event()
        self._prime_first_semantic_displayed = threading.Event()
        self._release_leader = threading.Event()
        self._leader_done = threading.Event()
        self._release_semantic = threading.Event()
        self._semantic_done = threading.Event()
        self._stop = threading.Event()
        self._error: BaseException | None = None
        self._primed_first_semantic_pair: FramePair | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> PairRenderCoordinator:
        self.engine.release_context()
        self._thread.start()
        return self

    def wait_until_ready(self, timeout_s: float = 1.0) -> bool:
        ready = self._ready.wait(timeout=timeout_s)
        self._raise_if_failed()
        return ready

    def release_startup_leader(self) -> None:
        """Open gate 1: end the phase 1 hold and start the leader VSYNC count."""
        self._release_leader.set()

    def wait_leader_done(self, timeout_s: float | None = 5.0) -> bool:
        """Block until all startup_leader_vsyncs leader frames have been shown."""
        done = self._leader_done.wait(timeout=timeout_s)
        self._raise_if_failed()
        return done

    def release_semantic_frames(self) -> None:
        """Open gate 2: end the phase 2b hold and start semantic playback.

        Also opens gate 1, since semantic frames can never precede the leader.
        """
        self._release_leader.set()
        self._release_semantic.set()

    def wait_semantic_frames_done(self, timeout_s: float | None = None) -> bool:
        """Block until semantic playback has displayed every frame.

        Defaults to waiting indefinitely. Returns False on timeout, and re-raises
        a render-thread exception the same way wait_leader_done() does.

        This resolves once the last semantic frame is on screen; join() then
        waits for the thread itself to unwind and release the GL context.
        """
        done = self._semantic_done.wait(timeout=timeout_s)
        self._raise_if_failed()
        return done

    def prime_first_semantic_frame(self, timeout_s: float = 1.0) -> bool:
        self._prime_first_semantic.set()
        displayed = self._prime_first_semantic_displayed.wait(timeout=timeout_s)
        self._raise_if_failed()
        return displayed

    def join(self) -> None:
        self._thread.join()
        self._raise_if_failed()

    def stop(self, timeout_s: float = 1.0) -> None:
        self._stop.set()
        self._release_leader.set()
        self._release_semantic.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout_s)

    def _raise_if_failed(self) -> None:
        if self._error is not None:
            raise self._error

    def _engine_should_close(self) -> bool:
        should_close = getattr(self.engine, "should_close", None)
        return bool(should_close()) if should_close is not None else False

    def _run(self) -> None:
        try:
            self.engine.make_context_current()
            self._ready.set()
            # Nothing displayed before `release_semantic_frames()` is allowed to
            # consume provider frames. The sequencers may not be running yet, and
            # any triggers emitted during the startup leader are intentionally
            # non-semantic and skipped by downstream camera processing.
            self._run_startup_pair_until_released()
            self._run_startup_leader()
            self._leader_done.set()
            self._run_leader_hold_until_released()
            self._run_semantic_frames()
            self._semantic_done.set()
        except BaseException as exc:
            self._error = exc
        finally:
            self._leader_done.set()
            self._semantic_done.set()
            try:
                self.engine.release_context()
            except Exception:
                pass

    def _run_startup_pair_until_released(self) -> None:
        while (
            not self._stop.is_set()
            and not self._release_leader.is_set()
            and not self._engine_should_close()
        ):
            if self._prime_first_semantic.is_set():
                _display_frame_pair(self.engine, self._first_semantic_pair())
                self._prime_first_semantic_displayed.set()
            else:
                _display_frame_pair(self.engine, self.startup_leader_pair)

    def _run_startup_leader(self) -> None:
        for _ in range(max(0, self.startup_leader_vsyncs)):
            if self._stop.is_set() or self._engine_should_close():
                return
            _display_frame_pair(self.engine, self.startup_leader_pair)

    def _run_leader_hold_until_released(self) -> None:
        """Hold the leader pair between the leader count and semantic playback."""
        while (
            not self._stop.is_set()
            and not self._release_semantic.is_set()
            and not self._engine_should_close()
        ):
            _display_frame_pair(self.engine, self.startup_leader_pair)

    def _run_semantic_frames(self) -> None:
        displayed = 0
        end_t = (
            None
            if MAX_RUNTIME_SECONDS <= 0
            else time.time() + MAX_RUNTIME_SECONDS
        )
        first_semantic_frame = self._primed_first_semantic_pair is None
        while (
            not self._stop.is_set()
            and (self.semantic_frames <= 0 or displayed < self.semantic_frames) # semantic frames <= 0 means run forever
            and not self._engine_should_close()
        ):
            displayed += 1
            if first_semantic_frame:
                frame_pair = self._first_semantic_pair()
                first_semantic_frame = False
            else:
                frame_pair = as_frame_pair(self.provider.next_pair())
            _display_frame_pair(self.engine, frame_pair)

    def _first_semantic_pair(self) -> FramePair:
        if self._primed_first_semantic_pair is None:
            self._primed_first_semantic_pair = as_frame_pair(
                self.provider.initial_pair()
            )
        return self._primed_first_semantic_pair


def _start_pair_render_coordinator(
    engine: Any,
    provider: PairFrameProvider,
    *,
    startup_leader_pair: FramePair | tuple[RGBFrame, RGBFrame],
    startup_leader_vsyncs: int,
    semantic_frames: int,
) -> PairRenderCoordinator:
    return PairRenderCoordinator(
        engine,
        provider,
        startup_leader_pair=startup_leader_pair,
        startup_leader_vsyncs=startup_leader_vsyncs,
        semantic_frames=semantic_frames,
    ).start()
