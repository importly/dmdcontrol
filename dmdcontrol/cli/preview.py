from __future__ import annotations


def serve(argv: list[str]) -> int | None:
    from dmdcontrol.preview import server

    return server.main(argv)
