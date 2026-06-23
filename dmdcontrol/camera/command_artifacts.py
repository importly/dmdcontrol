from __future__ import annotations

import shlex
import sys


def camera_command_argv(subcommand: str, argv: list[str] | None) -> list[str]:
    if argv is None:
        return sys.argv
    return ["python", "-m", "dmdcontrol", "camera", subcommand, *argv]


def command_text(command: list[str]) -> str:
    return shlex.join(command) + "\n"
