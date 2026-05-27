from __future__ import annotations

from types import ModuleType


def _single_runtime() -> ModuleType:
    from dmdcontrol.runtime import single

    return single


def run(argv: list[str]) -> int | None:
    return _single_runtime().main(argv)
