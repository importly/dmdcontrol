from pathlib import Path
from types import SimpleNamespace

from dmdcontrol.camera import usb_reset


def _write_device(root, name, *, serial="CAM123", product="DVXplorer"):
    device = root / name
    device.mkdir(parents=True)
    (device / "busnum").write_text("1\n", encoding="ascii")
    (device / "devnum").write_text("7\n", encoding="ascii")
    (device / "idVendor").write_text("152a\n", encoding="ascii")
    (device / "idProduct").write_text("8410\n", encoding="ascii")
    (device / "manufacturer").write_text("iniVation\n", encoding="ascii")
    (device / "product").write_text(f"{product}\n", encoding="ascii")
    (device / "serial").write_text(f"{serial}\n", encoding="ascii")
    (device / "authorized").write_text("1\n", encoding="ascii")
    return device


def _dv_with_descriptor(serial="CAM123", dev_address=None):
    descriptor = SimpleNamespace(serialNumber=serial, cameraModel="DVXplorer")
    if dev_address is not None:
        descriptor.devAddress = dev_address
    return SimpleNamespace(
        io=SimpleNamespace(
            camera=SimpleNamespace(discover=lambda: [descriptor]),
        ),
    )


def test_reset_camera_usb_uses_usbdevfs_reset_ioctl(monkeypatch, tmp_path):
    sysfs_root = tmp_path / "sys" / "bus" / "usb" / "devices"
    dev_root = tmp_path / "dev" / "bus" / "usb"
    _write_device(sysfs_root, "1-2")

    opened = []
    ioctl_calls = []
    closed = []
    monkeypatch.setattr(usb_reset.sys, "platform", "linux")
    monkeypatch.setattr(usb_reset.os, "open", lambda path, flags: opened.append((path, flags)) or 9)
    monkeypatch.setattr(usb_reset.fcntl, "ioctl", lambda fd, request, arg: ioctl_calls.append((fd, request, arg)))
    monkeypatch.setattr(usb_reset.os, "close", lambda fd: closed.append(fd))
    monkeypatch.setattr(usb_reset.time, "sleep", lambda seconds: None)

    result = usb_reset.reset_camera_usb(
        _dv_with_descriptor(),
        sysfs_root=sysfs_root,
        dev_bus_usb_root=dev_root,
    )

    assert result["success"] is True
    assert result["method"] == "ioctl"
    assert opened == [(str(Path(dev_root) / "001" / "007"), usb_reset.os.O_WRONLY)]
    assert ioctl_calls == [(9, usb_reset.USBDEVFS_RESET, 0)]
    assert closed == [9]


def test_reset_camera_usb_falls_back_to_authorized_toggle(monkeypatch, tmp_path):
    sysfs_root = tmp_path / "sys" / "bus" / "usb" / "devices"
    dev_root = tmp_path / "dev" / "bus" / "usb"
    device = _write_device(sysfs_root, "1-2")

    monkeypatch.setattr(usb_reset.sys, "platform", "linux")
    monkeypatch.setattr(usb_reset.os, "open", lambda path, flags: (_ for _ in ()).throw(PermissionError("no access")))
    monkeypatch.setattr(usb_reset.time, "sleep", lambda seconds: None)

    result = usb_reset.reset_camera_usb(
        _dv_with_descriptor(),
        sysfs_root=sysfs_root,
        dev_bus_usb_root=dev_root,
    )

    assert result["success"] is True
    assert result["method"] == "authorized"
    assert device.joinpath("authorized").read_text(encoding="ascii") == "1\n"
    assert result["errors"]


def test_reset_camera_usb_skips_non_linux(monkeypatch, tmp_path):
    monkeypatch.setattr(usb_reset.sys, "platform", "win32")

    result = usb_reset.reset_camera_usb(
        _dv_with_descriptor(),
        sysfs_root=tmp_path,
        dev_bus_usb_root=tmp_path,
    )

    assert result["attempted"] is False
    assert result["success"] is False


def test_run_power_cycle_command_executes_split_command(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(usb_reset.subprocess, "run", fake_run)
    monkeypatch.setattr(usb_reset.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))

    result = usb_reset.run_power_cycle_command("uhubctl -l 1-2 -p 3 -a cycle -d 2")

    assert result["success"] is True
    assert calls[0][0] == ["uhubctl", "-l", "1-2", "-p", "3", "-a", "cycle", "-d", "2"]
    assert calls[1] == ("sleep", 1.0)


def test_run_power_cycle_command_skips_empty_command():
    result = usb_reset.run_power_cycle_command(None)

    assert result["attempted"] is False
    assert result["success"] is False
