from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# remove completely later

try:
    import fcntl
except ImportError:
    class _MissingFcntl:
        @staticmethod
        def ioctl(*_args):
            raise OSError("fcntl is unavailable on this platform")

    fcntl = _MissingFcntl()


USBDEVFS_RESET = (ord("U") << 8) | 20


@dataclass(frozen=True)
class UsbResetResult:
    attempted: bool
    success: bool
    method: str | None = None
    device_path: str | None = None
    sysfs_path: str | None = None
    serial: str | None = None
    product: str | None = None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PowerCycleCommandResult:
    attempted: bool
    success: bool
    command: str | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _UsbDevice:
    sysfs_path: Path
    busnum: int
    devnum: int
    vendor: str | None
    product_id: str | None
    manufacturer: str | None
    product: str | None
    serial: str | None


def reset_camera_usb(
        dv,
        *,
        enabled=True,
        method="auto",
        settle_s=1.0,
        sysfs_root=Path("/sys/bus/usb/devices"),
        dev_bus_usb_root=Path("/dev/bus/usb"),
):
    if not enabled:
        return UsbResetResult(attempted=False, success=False, errors=("disabled",)).to_dict()
    if sys.platform != "linux":
        return UsbResetResult(attempted=False, success=False, errors=(f"unsupported platform: {sys.platform}",)).to_dict()
    if method not in {"auto", "ioctl", "authorized"}:
        raise ValueError("method must be one of: auto, ioctl, authorized")

    descriptor = _first_camera_descriptor(dv)
    devices = _list_usb_devices(sysfs_root)
    selected = _select_usb_device(devices, descriptor)
    if selected is None:
        return UsbResetResult(
            attempted=True,
            success=False,
            errors=("no matching USB camera device found in sysfs",),
        ).to_dict()

    errors = []
    if method in {"auto", "ioctl"}:
        result = _reset_with_ioctl(selected, dev_bus_usb_root, settle_s)
        if result.success or method == "ioctl":
            return result.to_dict()
        errors.extend(result.errors)

    if method in {"auto", "authorized"}:
        result = _reset_with_authorized(selected, settle_s)
        if errors and result.errors:
            result = UsbResetResult(
                attempted=result.attempted,
                success=result.success,
                method=result.method,
                device_path=result.device_path,
                sysfs_path=result.sysfs_path,
                serial=result.serial,
                product=result.product,
                errors=tuple(errors) + result.errors,
            )
        elif errors:
            result = UsbResetResult(
                attempted=result.attempted,
                success=result.success,
                method=result.method,
                device_path=result.device_path,
                sysfs_path=result.sysfs_path,
                serial=result.serial,
                product=result.product,
                errors=tuple(errors),
            )
        return result.to_dict()

    return UsbResetResult(
        attempted=True,
        success=False,
        sysfs_path=str(selected.sysfs_path),
        serial=selected.serial,
        product=selected.product,
        errors=tuple(errors),
    ).to_dict()


def run_power_cycle_command(command, *, timeout_s=15.0, settle_s=1.0):
    if not command:
        return PowerCycleCommandResult(attempted=False, success=False).to_dict()
    try:
        completed = subprocess.run(
            shlex.split(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except Exception as exc:
        return PowerCycleCommandResult(
            attempted=True,
            success=False,
            command=command,
            error=repr(exc),
        ).to_dict()
    if completed.returncode == 0 and settle_s > 0:
        time.sleep(settle_s)
    return PowerCycleCommandResult(
        attempted=True,
        success=completed.returncode == 0,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout[-1000:],
        stderr=completed.stderr[-1000:],
    ).to_dict()


def _first_camera_descriptor(dv):
    try:
        descriptors = dv.io.camera.discover()
    except Exception:
        return None
    if not descriptors:
        return None
    return descriptors[0]


def _list_usb_devices(sysfs_root):
    root = Path(sysfs_root)
    if not root.exists():
        return []
    devices = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        busnum = _read_int(path / "busnum")
        devnum = _read_int(path / "devnum")
        if busnum is None or devnum is None:
            continue
        devices.append(
            _UsbDevice(
                sysfs_path=path,
                busnum=busnum,
                devnum=devnum,
                vendor=_read_text(path / "idVendor"),
                product_id=_read_text(path / "idProduct"),
                manufacturer=_read_text(path / "manufacturer"),
                product=_read_text(path / "product"),
                serial=_read_text(path / "serial"),
            )
        )
    return devices


def _select_usb_device(devices, descriptor):
    descriptor_serial = _descriptor_text(descriptor, "serialNumber")
    descriptor_model = _descriptor_text(descriptor, "cameraModel")
    descriptor_address = _descriptor_text(descriptor, "devAddress")

    if descriptor_serial:
        matches = [device for device in devices if device.serial == descriptor_serial]
        if len(matches) == 1:
            return matches[0]

    if descriptor_address:
        address_match = _match_by_address(devices, descriptor_address)
        if address_match is not None:
            return address_match

    camera_matches = [
        device for device in devices
        if _looks_like_event_camera(device, descriptor_model)
    ]
    if len(camera_matches) == 1:
        return camera_matches[0]

    return None


def _match_by_address(devices, descriptor_address):
    numbers = [int(value) for value in re.findall(r"\d+", str(descriptor_address))]
    if len(numbers) < 2:
        return None
    bus, dev = numbers[-2], numbers[-1]
    matches = [
        device for device in devices
        if device.busnum == bus and device.devnum == dev
    ]
    return matches[0] if len(matches) == 1 else None


def _looks_like_event_camera(device, descriptor_model):
    haystack = " ".join(
        value.lower()
        for value in (device.manufacturer, device.product, device.serial, descriptor_model)
        if value
    )
    return any(token in haystack for token in ("inivation", "dvxplorer", "davis", "dvs"))


def _reset_with_ioctl(device, dev_bus_usb_root, settle_s):
    device_path = Path(dev_bus_usb_root) / f"{device.busnum:03d}" / f"{device.devnum:03d}"
    try:
        fd = os.open(str(device_path), os.O_WRONLY)
        try:
            fcntl.ioctl(fd, USBDEVFS_RESET, 0)
        finally:
            os.close(fd)
        if settle_s > 0:
            time.sleep(settle_s)
        return _result(device, "ioctl", device_path=device_path, success=True)
    except Exception as exc:
        return _result(
            device,
            "ioctl",
            device_path=device_path,
            success=False,
            errors=(repr(exc),),
        )


def _reset_with_authorized(device, settle_s):
    authorized_path = device.sysfs_path / "authorized"
    try:
        authorized_path.write_text("0\n", encoding="ascii")
        time.sleep(0.25)
        authorized_path.write_text("1\n", encoding="ascii")
        if settle_s > 0:
            time.sleep(settle_s)
        return _result(device, "authorized", success=True)
    except Exception as exc:
        return _result(device, "authorized", success=False, errors=(repr(exc),))


def _result(device, method, *, success, device_path=None, errors=()):
    return UsbResetResult(
        attempted=True,
        success=success,
        method=method,
        device_path=str(device_path) if device_path is not None else None,
        sysfs_path=str(device.sysfs_path),
        serial=device.serial,
        product=device.product,
        errors=tuple(errors),
    )


def _descriptor_text(descriptor, name):
    if descriptor is None:
        return None
    value = getattr(descriptor, name, None)
    if value is None:
        return None
    return str(value)


def _read_text(path):
    try:
        return Path(path).read_text(encoding="ascii").strip()
    except OSError:
        return None


def _read_int(path):
    text = _read_text(path)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None
