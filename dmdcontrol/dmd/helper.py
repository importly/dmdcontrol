"""DLPC900 USB selection by physical port."""

import logging
import re
from pathlib import Path
import usb.core
from dmdcontrol.utils import CONFIG

logger = logging.getLogger(__name__)


def physical_port(usb_devpath: Path | str) -> tuple[int, tuple[int, ...]]:
    """(bus, port_numbers) from a devpath fragment or full udev DEVPATH.
    `/usb1/1-8/1-8:1.0/` -> (1, (8,)); `/usb3/3-2.4/3-2.4:1.0/` -> (3, (2, 4))."""
    match = re.search(r"/usb(\d+)/(?:[^/]+/)*\d+-([0-9.]+):\d+\.\d+(?:/|$)", Path(usb_devpath).as_posix())
    if not match:
        raise ValueError(f"usb_devpath {str(usb_devpath)!r} is not of the form /usbB/B-P[.P]/B-P[.P]:C.I/")
    return int(match.group(1)), tuple(int(part) for part in match.group(2).split("."))


def dlpc900_devices() -> list[usb.core.Device]:
    """All DLPC900s pyusb can see (VID/PID from config)."""
    return list(usb.core.find(find_all=True, idVendor=CONFIG['DMD']['VID'], idProduct=CONFIG['DMD']['PID']) or [])


def select_pyusb_device(usb_devpath: Path | str) -> usb.core.Device:
    """The DLPC900 plugged into the port described by `usb_devpath`.

    Raises:
        RuntimeError: no (or more than one) DLPC900 on that port.
    """
    bus, ports = physical_port(usb_devpath)
    devices = dlpc900_devices()
    matches = [d for d in devices if d.bus == bus and tuple(d.port_numbers or ()) == ports]
    if len(matches) != 1:
        seen = ", ".join(f"bus {d.bus} ports {tuple(d.port_numbers or ())}" for d in devices) or "<none>"
        raise RuntimeError(
            f"{len(matches)} DLPC900 devices on bus {bus} ports {ports} (usb_devpath={str(usb_devpath)!r}); "
            f"pyusb sees: {seen}")
    logger.info("Selected DLPC900 on bus %d ports %s (address %d)", bus, ports, matches[0].address)
    return matches[0]


if __name__ == "__main__":
    for d in dlpc900_devices():
        ports = ".".join(str(p) for p in (d.port_numbers or ()))
        print(f"bus {d.bus} address {d.address:3d}  ->  usb_devpath: /usb{d.bus}/{d.bus}-{ports}/{d.bus}-{ports}:1.0/")
