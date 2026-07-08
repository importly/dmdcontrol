"""Reusable calibration-square runtime helpers.

This module is intentionally free of OpenGL imports at module import time. The
interactive provider imports GLFW only when calibration-square playback is
actually constructed.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from typing import Any, NamedTuple

from dmdcontrol.patterns.bitplanes import RGBFrameArray
from dmdcontrol.patterns.modes import (
    CalibrationSquareState,
    apply_calibration_square_commands,
    calibration_square_bounds,
    default_calibration_square_state,
    generate_calibration_square_mask,
)
from dmdcontrol.support.constants import BITPLANES
from dmdcontrol.support.logging import logger

VALID_CALIBRATION_COMMANDS = {"w", "a", "s", "d", "q", "e", "r", "f", "x"}


FrameProvider = Callable[[], RGBFrameArray]


class CalibrationControlRead(NamedTuple):
    commands: str
    offset: int


@dataclass
class CalibrationSquareProviderState:
    square: CalibrationSquareState
    frame: RGBFrameArray
    control_offset: int = 0
    last_log: float = 0.0


def build_calibration_square_frame(
    engine: Any,
    state: CalibrationSquareState,
    bitplanes: int = BITPLANES,) -> RGBFrameArray:
    mask = generate_calibration_square_mask(
        width=engine.width,
        height=engine.height,
        center_x=state.x,
        center_y=state.y,
        size_px=state.size,
        angle_deg=state.angle_deg,
    )
    return engine.pack_patterns([mask] * bitplanes)


def format_calibration_square_state(
    state: CalibrationSquareState,
    width: int,
    height: int,) -> str:
    left, top, right, bottom = calibration_square_bounds(state, width, height)
    return (
        f"center=({state.x:.0f},{state.y:.0f}) px, "
        f"bounds=({left},{top})..({right},{bottom}) px, "
        f"size={state.size:.0f}px, angle={state.angle_deg:.1f}deg")


def read_calibration_square_control_file(
    path: str | PathLike[str] | None,
    offset: int,) -> CalibrationControlRead:
    if not path:
        return CalibrationControlRead("", offset)
    try:
        size = os.path.getsize(path)
        if size < offset:
            offset = 0
        with open(path, "r", encoding="ascii", errors="ignore") as f:
            f.seek(offset)
            data = f.read()
            offset = f.tell()
    except OSError as exc:
        logger.warning(f"[CALIBRATION] Cannot read control file {path}: {exc}")
        return CalibrationControlRead("", offset)
    commands = "".join(ch.lower() for ch in data if ch.lower() in VALID_CALIBRATION_COMMANDS)
    return CalibrationControlRead(commands, offset)


def calibration_square_key_commands(glfw: Any) -> tuple[tuple[int, str], ...]:
    return (
        (glfw.KEY_W,
         "w"),
        (glfw.KEY_A,
         "a"),
        (glfw.KEY_S,
         "s"),
        (glfw.KEY_D,
         "d"),
        (glfw.KEY_Q,
         "q"),
        (glfw.KEY_E,
         "e"),
        (glfw.KEY_R,
         "r"),
        (glfw.KEY_F,
         "f"),
    )


def make_calibration_square_frame_provider(
    engine: Any,
    initial_frame: RGBFrameArray,
    control_file: str | PathLike[str] | None = None,
    initial_state: CalibrationSquareState | None = None,) -> FrameProvider:
    import glfw

    key_commands = calibration_square_key_commands(glfw)
    state = CalibrationSquareProviderState(
        square=initial_state or default_calibration_square_state(engine.width, engine.height),
        frame=initial_frame,
    )

    def _provider_calibration_square() -> RGBFrameArray:
        file_read = read_calibration_square_control_file(
            control_file,
            state.control_offset,
        )
        file_commands = file_read.commands
        state.control_offset = file_read.offset
        keyboard_commands = "".join(
            command for key, command in key_commands
            if glfw.get_key(engine.window, key) == glfw.PRESS)
        commands = file_commands + keyboard_commands
        if "x" in commands:
            logger.info("[CALIBRATION] Exit requested from calibration control input.")
            glfw.set_window_should_close(engine.window, True)
            commands = commands.replace("x", "")
        if commands:
            state.square = apply_calibration_square_commands(
                state.square,
                commands,
                width=engine.width,
                height=engine.height,
            )
            state.frame = build_calibration_square_frame(engine, state.square)
            now = time.monotonic()
            if file_commands or now - state.last_log >= 0.25:
                logger.info(
                    "[CALIBRATION] square "
                    f"{format_calibration_square_state(state.square, engine.width, engine.height)}"
                )
                state.last_log = now
        return state.frame

    return _provider_calibration_square
