from __future__ import annotations

from dmdcontrol.preview.server import main as server_main


def serve(argv: list[str]) -> int | None:
    return server_main(argv)
