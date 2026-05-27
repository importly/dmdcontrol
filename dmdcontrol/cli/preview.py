from __future__ import annotations

import importlib


def serve(argv: list[str]) -> int | None:
    legacy = importlib.import_module("dmd_preview_server")
    return legacy.main(argv)
