from __future__ import annotations

from types import ModuleType


def _flood_module() -> ModuleType:
    from dmdcontrol.hardware import flood

    return flood


def run(argv: list[str]) -> int | None:
    return _flood_module().main(argv)
