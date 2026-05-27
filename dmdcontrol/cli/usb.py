from __future__ import annotations

import importlib


def discover(argv: list[str]) -> int | None:
    legacy = importlib.import_module("dmd_usb")
    return legacy.main(argv)


def wake(argv: list[str]) -> int | None:
    legacy = importlib.import_module("wake_dp")
    return legacy.main(argv)
