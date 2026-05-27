from __future__ import annotations

from dmdcontrol.hardware import usb as dmd_usb
from dmdcontrol.hardware import wake as wake_dp


def discover(argv: list[str]) -> int | None:
    return dmd_usb.main(argv)


def wake(argv: list[str]) -> int | None:
    return wake_dp.main(argv)
