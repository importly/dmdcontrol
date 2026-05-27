from __future__ import annotations

from dmdcontrol.runtime import single


def run(argv: list[str]) -> int | None:
    return single.main(argv)
