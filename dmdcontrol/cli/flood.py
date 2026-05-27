from __future__ import annotations

import importlib


def run(argv: list[str]) -> int | None:
    legacy = importlib.import_module("flood_white_usb")
    return legacy.main(argv)
