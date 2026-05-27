from __future__ import annotations

from types import ModuleType


def _preview_server() -> ModuleType:
    from dmdcontrol.preview import server

    return server


def serve(argv: list[str]) -> int | None:
    return _preview_server().main(argv)
