from __future__ import annotations

from dmdcontrol.preview import server


def serve(argv: list[str]) -> int | None:
    return server.main(argv)
