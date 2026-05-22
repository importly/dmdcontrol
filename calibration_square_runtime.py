"""Reusable calibration-square runtime helpers.

This module is intentionally free of OpenGL imports at module import time. The
interactive provider imports GLFW only when calibration-square playback is
actually constructed.
"""

import os
import time

from config import BITPLANES
from logger import logger
from pattern_modes import (
    apply_calibration_square_commands,
    calibration_square_bounds,
    default_calibration_square_state,
    generate_calibration_square_mask,
)

VALID_CALIBRATION_COMMANDS = {"w", "a", "s", "d", "q", "e", "r", "f", "x"}


def build_calibration_square_frame(engine, state, bitplanes=BITPLANES):
    mask = generate_calibration_square_mask(
        width=engine.width,
        height=engine.height,
        center_x=state.x,
        center_y=state.y,
        size_px=state.size,
        angle_deg=state.angle_deg,
    )
    return engine.pack_patterns([mask] * bitplanes)


def format_calibration_square_state(state, width, height):
    left, top, right, bottom = calibration_square_bounds(state, width, height)
    return (
        f"center=({state.x:.0f},{state.y:.0f}) px, "
        f"bounds=({left},{top})..({right},{bottom}) px, "
        f"size={state.size:.0f}px, angle={state.angle_deg:.1f}deg"
    )


def read_calibration_square_control_file(path, offset):
    if not path:
        return "", offset
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
        return "", offset
    commands = "".join(
        ch.lower() for ch in data if ch.lower() in VALID_CALIBRATION_COMMANDS
    )
    return commands, offset


def calibration_square_key_commands(glfw):
    return (
        (glfw.KEY_W, "w"),
        (glfw.KEY_A, "a"),
        (glfw.KEY_S, "s"),
        (glfw.KEY_D, "d"),
        (glfw.KEY_Q, "q"),
        (glfw.KEY_E, "e"),
        (glfw.KEY_R, "r"),
        (glfw.KEY_F, "f"),
    )


def make_calibration_square_frame_provider(
    engine,
    initial_frame,
    control_file=None,
    initial_state=None,
):
    import glfw

    key_commands = calibration_square_key_commands(glfw)
    state = {
        "square": initial_state
        or default_calibration_square_state(engine.width, engine.height),
        "frame": initial_frame,
        "control_offset": 0,
        "last_log": 0.0,
    }

    def _provider_calibration_square():
        file_commands, state["control_offset"] = read_calibration_square_control_file(
            control_file,
            state["control_offset"],
        )
        keyboard_commands = "".join(
            command
            for key, command in key_commands
            if glfw.get_key(engine.window, key) == glfw.PRESS
        )
        commands = file_commands + keyboard_commands
        if "x" in commands:
            logger.info("[CALIBRATION] Exit requested from calibration control input.")
            glfw.set_window_should_close(engine.window, True)
            commands = commands.replace("x", "")
        if commands:
            state["square"] = apply_calibration_square_commands(
                state["square"],
                commands,
                width=engine.width,
                height=engine.height,
            )
            state["frame"] = build_calibration_square_frame(engine, state["square"])
            now = time.monotonic()
            if file_commands or now - state["last_log"] >= 0.25:
                logger.info(
                    "[CALIBRATION] square "
                    f"{format_calibration_square_state(state['square'], engine.width, engine.height)}"
                )
                state["last_log"] = now
        return state["frame"]

    return _provider_calibration_square
