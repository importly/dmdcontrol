"""DLPC900 USB discovery and explicit physical-port selection helpers."""

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple
import usb.core
from dmdcontrol.utils.constants import DLPC900_PID, DLPC900_VID


@dataclass(frozen=True)
class UsbDevice:
    vid: int
    pid: int
    bus: int
    address: int
    serial: str
    hidraw: Path
    id_path: str
    devpath: Path
    physical_path: Path
    

def parse_physical_usb_path(physical_path) -> PhysicalUsbPath | None:
    match = re.fullmatch(r"usb(\d+)/\d+-([0-9.]+)", physical_path or "")
    if not match:
        return None
    bus = int(match.group(1))
    ports = tuple(int(part) for part in match.group(2).split(".") if part)
    return PhysicalUsbPath(bus, ports)


def _udevadm_properties_for_hidraw(hidraw: Path | str) -> dict[str, str]:
    """
    Grab properties from `udevadm`

    Args:
        hidraw (Path | str): The path to the hidraw device.

    Raises:
        RuntimeError: If `udevadm` fails to retrieve properties for the given hidraw device.

    Returns:
        dict[str, str]: A dictionary of properties for the given hidraw device.
    """
    result = subprocess.run(
        ["udevadm",
         "info",
         "--query=property",
         f"--name={hidraw}"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"udevadm failed for {hidraw}")
    
    text = result.stdout
    
    props = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        props[key] = value
        
    return props



def discover_dlpc900_usb() -> list[UsbDevice]:
    """
    Discover DLPC900 devices connected via USB.

    Returns:
        list[UsbDevice]: A list of discovered DLPC900 USB devices.
    """
    # Make paths
    dev_path = Path('/dev')
    sys_root = Path('/sys')
        
    # Discover hidraw paths under /dev and /sys/class/hidraw
    sys_hidraw_path = Path(sys_root) / "class" / "hidraw"
    hidraw_nodes = sorted(dev_path.glob("hidraw*"))
    if not hidraw_nodes and sys_hidraw_path.exists():
        hidraw_nodes = [dev_path / path.name for path in sorted(sys_hidraw_path.glob("hidraw*"))]
        
    # Grab properties for each hidraw node and filter for DLPC900 devices
    candidates = []
    for hidraw in hidraw_nodes:
        props = _udevadm_properties_for_hidraw(hidraw)
        vendor = int(props.get("ID_VENDOR_ID"), 16)
        model = int(props.get("ID_MODEL_ID"), 16)
        if vendor != DLPC900_VID or model != DLPC900_PID:
            continue
        else:
            # Get the DEVPATH, then strip it back to the parent USB device path
            devpath = Path(props.get("DEVPATH"))
            usb_devpath = devpath.parents[3].relative_to('/')
            
            # Read the bus and address
            bus = int((Path('/sys') / usb_devpath / "busnum").read_text(encoding="ascii").strip())
            address = int((Path('/sys') / usb_devpath / "devnum").read_text(encoding="ascii").strip())
            
            candidate = UsbDevice(
                vid=vendor,
                pid=model,
                bus=bus,
                address=address,
                serial=props.get("ID_SERIAL_SHORT"),
                hidraw=Path(props.get("DEVNAME")),
                id_path=props.get("ID_PATH"),
                devpath=devpath,
                physical_path=Path(*devpath.parts[5:7]),
            )
            candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda c: (c.id_path or "", c.hidraw or "", c.bus or -1, c.address or -1),
    )


def select_pyusb_device_for_mapping(usb_id_path: str, usb_devpath: Path | str) -> usb.core.Device:
    """
    Returns the PyUSB device that matches the given USB mapping.

    Args:
        usb_id_path (str): The USB ID path of the device.
        usb_devpath (Path | str): The USB device path of the device.

    Raises:
        RuntimeError: If no matching DLPC900 USB devices are found or if multiple matching devices are found.
        RuntimeError: If the PyUSB device cannot be found.

    Returns:
        usb.core.Device: The correct PyUSB device.
    """
    # Grab matching candidate from the discovered hidraw devices
    candidates = discover_dlpc900_usb()
    for candidate in candidates:
        if candidate.id_path != usb_id_path or candidate.devpath != usb_devpath:
            candidates.remove(candidate)
    
    # Error handling if there's no candidates or if there's more than one candidate
    if not candidates:
        raise RuntimeError(
            f"No DLPC900 USB devices found matching id_path={usb_id_path!r} and devpath={usb_devpath!r}")
    if len(candidates) > 1:
        raise RuntimeError(
            f"Multiple DLPC900 USB devices found matching id_path={usb_id_path!r} and devpath={usb_devpath!r}")

    # Select the PyUSB device that matches the candidate
    device = usb.core.find(
        find_all=True,
        idVendor=DLPC900_VID,
        idProduct=DLPC900_PID,
        custom_match=lambda d: d.bus == candidates[0].bus and d.address == candidates[0].address,
        )
    
    # Error handling if the PyUSB device cannot be found
    if device is None:
        raise RuntimeError(
            f"Found hidraw mapping {candidates[0].id_path}, but could not match it to a PyUSB device.")

    return device

def format_usb_candidates(candidates: list[UsbDevice]) -> str:
    """
    Formats the USB candidates to print out.

    Args:
        candidates (list[UsbDevice]): List of candidates to format.

    Returns:
        str: The formatted string of USB candidates.
    """
    lines = [f"Found {len(candidates)} DLPC900 USB devices:"]
    for index, candidate in enumerate(candidates):
        lines.extend(
            [
                "",
                f"[{index}]",
                f"  vidpid: {candidate.vid:04x}:{candidate.pid:04x}",
                f"  serial: {candidate.serial}",
                f"  bus: {candidate.bus}",
                f"  dev: {candidate.address}",
                f"  hidraw: {candidate.hidraw}",
                f"  id_path: {candidate.id_path}",
                f"  devpath: {candidate.devpath}",
                f"  physical_path: {candidate.physical_path}",
                f"  suggested_config_key: {candidate.id_path}",
            ])
    return "\n".join(lines)


def main(argv=None):
    print(format_usb_candidates(discover_dlpc900_usb()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
