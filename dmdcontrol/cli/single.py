from __future__ import annotations

from dmdcontrol.runtime.single import main as runtime_main


def run(argv: list[str]) -> int | None:
    return runtime_main(argv)
