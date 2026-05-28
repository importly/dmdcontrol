import json
import tempfile
import unittest
from pathlib import Path

from dmdcontrol.hardware.mapping import resolve_dmd_mapping
from dmdcontrol.hardware.usb import (
    format_usb_candidates,
    parse_physical_usb_path,
    parse_udevadm_properties,
    physical_path_from_devpath,
    select_pyusb_device_for_mapping,
    usb_ids_from_properties,
)

UDEV_HIDRAW0 = """
DEVPATH=/devices/pci0000:00/0000:00:03.1/0000:03:00.0/usb1/1-1/1-1:1.0/0003:0451:C900.0001/hidraw/hidraw0
DEVNAME=/dev/hidraw0
ID_PATH=pci-0000:03:00.0-usb-0:1:1.0
ID_SERIAL_SHORT=C900
ID_VENDOR_ID=0451
ID_MODEL_ID=c900
"""


class _FakeUsbDevice:
    def __init__(self, bus, address, port_numbers):
        self.bus = bus
        self.address = address
        self.port_numbers = port_numbers


class DmdUsbMappingTests(unittest.TestCase):
    def test_parse_udev_properties_and_physical_path(self):
        props = parse_udevadm_properties(UDEV_HIDRAW0)

        self.assertEqual(props["ID_PATH"], "pci-0000:03:00.0-usb-0:1:1.0")
        self.assertEqual(props["ID_SERIAL_SHORT"], "C900")
        self.assertEqual(
            physical_path_from_devpath(props["DEVPATH"]),
            "usb1/1-1",
        )

    def test_usb_ids_parse_from_standard_and_hid_id_properties(self):
        props = parse_udevadm_properties(UDEV_HIDRAW0)
        self.assertEqual(usb_ids_from_properties(props), (0x0451, 0xC900))

        hid_props = parse_udevadm_properties(
            "HID_ID=0003:00000451:0000C900\nDEVNAME=/dev/hidraw1\n"
        )
        self.assertEqual(usb_ids_from_properties(hid_props), (0x0451, 0xC900))

    def test_physical_usb_path_parses_port_topology(self):
        self.assertEqual(parse_physical_usb_path("usb1/1-8"), (1, (8,)))
        self.assertEqual(parse_physical_usb_path("usb2/2-4.3"), (2, (4, 3)))

    def test_resolve_dmd_mapping_from_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "dmd_devices.json"
            config_path.write_text(
                json.dumps(
                    {
                        "dmds": {
                            "A": {
                                "usb_id_path": "pci-0000:03:00.0-usb-0:1:1.0",
                                "usb_devpath_contains": "/usb1/1-1/1-1:1.0/",
                                "xrandr_output": "DP-2",
                                "glfw_monitor_index": 0,
                                "target_hz": 60,
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            mapping = resolve_dmd_mapping("A", config_path)

        self.assertEqual(mapping.name, "A")
        self.assertEqual(mapping.usb_id_path, "pci-0000:03:00.0-usb-0:1:1.0")
        self.assertEqual(mapping.usb_devpath_contains, "/usb1/1-1/1-1:1.0/")
        self.assertEqual(mapping.xrandr_output, "DP-2")
        self.assertEqual(mapping.glfw_monitor_index, 0)
        self.assertEqual(mapping.target_hz, 60)

    def test_format_usb_candidates_matches_operator_shape(self):
        props = parse_udevadm_properties(UDEV_HIDRAW0)
        text = format_usb_candidates(
            [
                {
                    "vid": 0x0451,
                    "pid": 0xC900,
                    "bus": 1,
                    "address": 18,
                    "serial": props["ID_SERIAL_SHORT"],
                    "hidraw": props["DEVNAME"],
                    "id_path": props["ID_PATH"],
                    "devpath": props["DEVPATH"],
                    "physical_path": physical_path_from_devpath(props["DEVPATH"]),
                }
            ]
        )

        self.assertIn("Found 1 DLPC900 USB device", text)
        self.assertIn("vidpid: 0451:c900", text)
        self.assertIn("bus: 001", text)
        self.assertIn("dev: 018", text)
        self.assertIn("hidraw: /dev/hidraw0", text)
        self.assertIn("suggested_config_key: pci-0000:03:00.0-usb-0:1:1.0", text)

    def test_select_pyusb_device_falls_back_to_configured_physical_port(self):
        expected = _FakeUsbDevice(bus=1, address=18, port_numbers=(1,))
        other = _FakeUsbDevice(bus=1, address=19, port_numbers=(8,))

        selected = select_pyusb_device_for_mapping(
            "pci-0000:03:00.0-usb-0:1:1.0",
            usb_devpath_contains="/usb1/1-1/1-1:1.0/",
            candidates=[],
            pyusb_devices=[other, expected],
        )

        self.assertIs(selected, expected)


if __name__ == "__main__":
    unittest.main()
