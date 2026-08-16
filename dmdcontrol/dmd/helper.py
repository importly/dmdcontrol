"""DLPC900 USB selection by physical port."""

import logging
import usb.core
from dmdcontrol.utils import CONFIG

logger = logging.getLogger(__name__)


def dlpc900_devices() -> list[usb.core.Device]:
    """All DLPC900s pyusb can see (VID/PID from config)."""
    return list(usb.core.find(find_all=True, idVendor=CONFIG['DMD']['VID'], idProduct=CONFIG['DMD']['PID']) or []) # pyright: ignore


def select_pyusb_device(usb_bus: int, usb_port: tuple[int, ...]) -> usb.core.Device:
    """The DLPC900 plugged into `usb_port` of `usb_bus`.

    Raises:
        RuntimeError: no (or more than one) DLPC900 on that port.
    """
    devices = dlpc900_devices()
    matches = [d for d in devices if d.bus == usb_bus and tuple(d.port_numbers or ()) == usb_port] # pyright: ignore
    if len(matches) != 1:
        seen = ", ".join(f"bus {d.bus} port {list(d.port_numbers or ())}" for d in devices) or "<none>" # pyright: ignore
        raise RuntimeError(
            f"{len(matches)} DLPC900 devices on bus {usb_bus} port {list(usb_port)}; pyusb sees: {seen}")
    logger.info("Selected DLPC900 on bus %d port %s (address %d)", usb_bus, list(usb_port), matches[0].address)
    return matches[0]


if __name__ == "__main__":
    for d in dlpc900_devices():
        print(f"address {d.address:3d}  ->  usb_bus: {d.bus}   usb_port: {list(d.port_numbers or ())}") # pyright: ignore
