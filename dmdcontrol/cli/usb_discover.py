from __future__ import annotations

from dmdcontrol.hardware.usb import main as usb_main


def discover(argv: list[str]) -> int | None:
    return usb_main(argv)
