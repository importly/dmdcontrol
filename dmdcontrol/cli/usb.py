from __future__ import annotations

from types import ModuleType


def _usb_module() -> ModuleType:
    from dmdcontrol.hardware import usb

    return usb


def _wake_module() -> ModuleType:
    from dmdcontrol.hardware import wake

    return wake


def discover(argv: list[str]) -> int | None:
    return _usb_module().main(argv)


def wake(argv: list[str]) -> int | None:
    return _wake_module().main(argv)
