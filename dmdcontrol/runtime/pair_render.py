"""Paired render-thread coordination for startup and semantic playback."""

from __future__ import annotations

import argparse
import threading
import time
from typing import Any

import numpy as np

from dmdcontrol.patterns.paired import (
    FramePair,
    PairFrameProvider,
    RGBFrame,
    as_frame_pair,
)
from dmdcontrol.utils import CONFIG

DMD_WIDTH = CONFIG.get('DMD', {}).get('width')
DMD_HEIGHT = CONFIG.get('DMD', {}).get('height')


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
    """

    def __init__(
        self,
        engine: Any,
        provider: PairFrameProvider,
        args: argparse.Namespace,
        *,
        startup_leader_pair: FramePair | tuple[RGBFrame, RGBFrame],
        startup_leader_vsyncs: int,
    ) -> None:
        self.engine = engine
        self.provider = provider
        self.args = args
        self.startup_leader_pair = as_frame_pair(startup_leader_pair)
        self.startup_leader_vsyncs = int(startup_leader_vsyncs)
        self._ready = threading.Event()
        self._prime_first_semantic = threading.Event()
        self._prime_first_semantic_displayed = threading.Event()
        self._release_semantic = threading.Event()
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

    def release_semantic_frames(self) -> None:
        self._release_semantic.set()

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
            self._run_semantic_frames()
        except BaseException as exc:
            self._error = exc
        finally:
            try:
                self.engine.release_context()
            except Exception:
                pass

    def _run_startup_pair_until_released(self) -> None:
        while (
            not self._stop.is_set()
            and not self._release_semantic.is_set()
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

    def _run_semantic_frames(self) -> None:
        end_t = (
            None
            if self.args.runtime_seconds <= 0
            else time.time() + self.args.runtime_seconds
        )
        first_semantic_frame = self._primed_first_semantic_pair is None
        while (
            not self._stop.is_set()
            and (end_t is None or time.time() < end_t)
            and not self._engine_should_close()
        ):
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
    args: argparse.Namespace,
    *,
    startup_leader_pair: FramePair | tuple[RGBFrame, RGBFrame],
    startup_leader_vsyncs: int,
) -> PairRenderCoordinator:
    return PairRenderCoordinator(
        engine,
        provider,
        args,
        startup_leader_pair=startup_leader_pair,
        startup_leader_vsyncs=startup_leader_vsyncs,
    ).start()
