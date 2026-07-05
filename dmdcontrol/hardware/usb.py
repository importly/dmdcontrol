"""DLPC900 USB discovery and explicit physical-port selection helpers."""

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from dmdcontrol.support.constants import DLPC900_PID, DLPC900_VID


class UsbIds(NamedTuple):
    vid: int | None
    pid: int | None


class PhysicalUsbPath(NamedTuple):
    bus: int
    ports: tuple[int, ...]


@dataclass(frozen=True)
class UsbCandidate:
    vid: int
    pid: int
    bus: int | None = None
    address: int | None = None
    serial: str | None = None
    hidraw: str | None = None
    id_path: str | None = None
    devpath: str | None = None
    physical_path: str | None = None


def parse_udevadm_properties(text):
    props = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        props[key] = value
    return props


def usb_ids_from_properties(props) -> UsbIds:
    vendor = props.get("ID_VENDOR_ID")
    model = props.get("ID_MODEL_ID")
    if vendor and model:
        return UsbIds(int(vendor, 16), int(model, 16))

    hid_id = props.get("HID_ID")
    if hid_id:
        parts = hid_id.split(":")
        if len(parts) == 3:
            return UsbIds(int(parts[1], 16), int(parts[2], 16))

    return UsbIds(None, None)


def physical_path_from_devpath(devpath):
    if not devpath:
        return None
    match = re.search(r"/(usb\d+)/(?:[^/]+/)*([^/]+):\d+\.\d+(?:/|$)", devpath)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def parse_physical_usb_path(physical_path) -> PhysicalUsbPath | None:
    match = re.fullmatch(r"usb(\d+)/\d+-([0-9.]+)", physical_path or "")
    if not match:
        return None
    bus = int(match.group(1))
    ports = tuple(int(part) for part in match.group(2).split(".") if part)
    return PhysicalUsbPath(bus, ports)


def _usb_device_devpath_from_hid_devpath(devpath):
    if not devpath:
        return None
    parts = devpath.strip("/").split("/")
    for index, part in enumerate(parts):
        if re.fullmatch(r"\d+-[0-9.]+:\d+\.\d+", part):
            if index == 0:
                return None
            return "/" + "/".join(parts[:index])
    return None


def _read_int_file(path):
    try:
        return int(Path(path).read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return None


def _bus_address_from_devpath(devpath, sys_root="/sys"):
    usb_devpath = _usb_device_devpath_from_hid_devpath(devpath)
    if not usb_devpath:
        return None, None
    sys_path = Path(sys_root) / usb_devpath.strip("/")
    return _read_int_file(sys_path / "busnum"), _read_int_file(sys_path / "devnum")


def candidate_from_udev_properties(props, hidraw=None, sys_root="/sys"):
    vid, pid = usb_ids_from_properties(props)
    if vid is None or pid is None:
        return None
    devpath = props.get("DEVPATH")
    bus, address = _bus_address_from_devpath(devpath, sys_root=sys_root)
    return UsbCandidate(
        vid=vid,
        pid=pid,
        bus=bus,
        address=address,
        serial=props.get("ID_SERIAL_SHORT"),
        hidraw=hidraw or props.get("DEVNAME"),
        id_path=props.get("ID_PATH"),
        devpath=devpath,
        physical_path=physical_path_from_devpath(devpath),
    )


def _udevadm_properties_for_hidraw(hidraw):
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
    return parse_udevadm_properties(result.stdout)


def discover_dlpc900_usb(dev_dir="/dev", sys_root="/sys"):
    dev_path = Path(dev_dir)
    sys_hidraw_path = Path(sys_root) / "class" / "hidraw"
    hidraw_nodes = sorted(dev_path.glob("hidraw*"))
    if not hidraw_nodes and sys_hidraw_path.exists():
        hidraw_nodes = [dev_path / path.name for path in sorted(sys_hidraw_path.glob("hidraw*"))]
    candidates = []
    for hidraw_path in hidraw_nodes:
        hidraw = str(hidraw_path)
        props = _udevadm_properties_for_hidraw(hidraw)
        candidate = candidate_from_udev_properties(props, hidraw=hidraw, sys_root=sys_root)
        if candidate and candidate.vid == DLPC900_VID and candidate.pid == DLPC900_PID:
            candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda c: (c.id_path or "", c.hidraw or "", c.bus or -1, c.address or -1),
    )


def _coerce_candidate(candidate):
    if isinstance(candidate, UsbCandidate):
        return candidate
    return UsbCandidate(**candidate)


def resolve_usb_candidate(usb_id_path, usb_devpath_contains=None, candidates=None):
    if not usb_id_path:
        raise ValueError("usb_id_path is required for explicit DMD selection")
    if candidates is None:
        candidates = discover_dlpc900_usb()
    coerced = [_coerce_candidate(candidate) for candidate in candidates]
    matches = [
        candidate for candidate in coerced if candidate.id_path == usb_id_path and (
            not usb_devpath_contains or
            (candidate.devpath and usb_devpath_contains in candidate.devpath))]
    if not matches:
        discovered = ", ".join(
            f"{c.id_path or '<no ID_PATH>'} ({c.physical_path or '<no physical path>'})"
            for c in coerced)
        raise RuntimeError(
            f"Expected DLPC900 USB mapping not present: id_path={usb_id_path!r}, "
            f"devpath_contains={usb_devpath_contains!r}. Discovered: {discovered or '<none>'}")
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous DLPC900 USB mapping for id_path={usb_id_path!r}")
    return matches[0]


def _load_pyusb_devices(pyusb_devices=None):
    if pyusb_devices is not None:
        return list(pyusb_devices)
    import usb.core

    return list(usb.core.find(find_all=True, idVendor=DLPC900_VID, idProduct=DLPC900_PID) or [])


def _select_pyusb_device_by_physical_path(devices, physical_path):
    parsed_physical = parse_physical_usb_path(physical_path)
    if not parsed_physical:
        return None
    expected_bus, expected_ports = parsed_physical
    matches = []
    for device in devices:
        if getattr(device, "bus", None) != expected_bus:
            continue
        ports = getattr(device, "port_numbers", None)
        if ports is not None and tuple(ports) == expected_ports:
            matches.append(device)
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous DLPC900 PyUSB devices for physical path {physical_path!r}")
    return matches[0] if matches else None


def _select_pyusb_device_by_candidate(devices, candidate):
    if candidate.bus is not None and candidate.address is not None:
        for device in devices:
            if (getattr(device,
                        "bus",
                        None) == candidate.bus and getattr(device,
                                                           "address",
                                                           None) == candidate.address):
                return device
    return _select_pyusb_device_by_physical_path(devices, candidate.physical_path)


def select_pyusb_device_for_mapping(
    usb_id_path,
    usb_devpath_contains=None,
    candidates=None,
    pyusb_devices=None,
):
    devices = _load_pyusb_devices(pyusb_devices)
    try:
        candidate = resolve_usb_candidate(
            usb_id_path,
            usb_devpath_contains,
            candidates=candidates,
        )
    except RuntimeError as discovery_error:
        physical_path = physical_path_from_devpath(usb_devpath_contains)
        device = _select_pyusb_device_by_physical_path(devices, physical_path)
        if device is not None:
            return device
        raise discovery_error

    device = _select_pyusb_device_by_candidate(devices, candidate)
    if device is not None:
        return device

    raise RuntimeError(
        f"Found hidraw mapping {candidate.id_path}, but could not match it to a PyUSB device.")


def _format_int(value, width=3):
    return "unknown" if value is None else f"{int(value):0{width}d}"


def format_usb_candidates(candidates):
    coerced = [_coerce_candidate(candidate) for candidate in candidates]
    lines = [f"Found {len(coerced)} DLPC900 USB device{'s' if len(coerced) != 1 else ''}:"]
    for index, candidate in enumerate(coerced):
        lines.extend(
            [
                "",
                f"[{index}]",
                f"  vidpid: {candidate.vid:04x}:{candidate.pid:04x}",
                f"  serial: {candidate.serial or 'unknown'}",
                f"  bus: {_format_int(candidate.bus)}",
                f"  dev: {_format_int(candidate.address)}",
                f"  hidraw: {candidate.hidraw or 'unknown'}",
                f"  id_path: {candidate.id_path or 'unknown'}",
                f"  devpath: {candidate.devpath or 'unknown'}",
                f"  physical_path: {candidate.physical_path or 'unknown'}",
                f"  suggested_config_key: {candidate.id_path or 'unknown'}",
            ])
    return "\n".join(lines)


def _build_parser():
    parser = argparse.ArgumentParser(description="Discover DLPC900 USB HID devices")
    parser.add_argument("command", nargs="?", default="discover", choices=("discover", ))
    return parser


def main(argv=None):
    _build_parser().parse_args(argv)
    print(format_usb_candidates(discover_dlpc900_usb()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
