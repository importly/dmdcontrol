from __future__ import annotations

from dmdcontrol.hardware import flood


def run(argv: list[str]) -> int | None:
    return flood.main(argv)
