import json
import tempfile
import unittest
from pathlib import Path

from main_pair import resolve_pair_config


class MainPairConfigTests(unittest.TestCase):
    def test_resolve_pair_config_maps_b_left_and_a_right(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "dmd_devices.json"
            config_path.write_text(
                json.dumps(
                    {
                        "dmds": {
                            "A": {
                                "usb_id_path": "pci-a",
                                "usb_devpath_contains": "/usb1/1-1/",
                                "xrandr_output": "DP-2",
                                "glfw_monitor_index": 1,
                                "target_hz": 60,
                            },
                            "B": {
                                "usb_id_path": "pci-b",
                                "usb_devpath_contains": "/usb1/1-8/",
                                "xrandr_output": "DP-0",
                                "glfw_monitor_index": 0,
                                "target_hz": 60,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            config = resolve_pair_config(config_path)

        self.assertEqual(config.dmd_a.xrandr_output, "DP-2")
        self.assertEqual(config.dmd_b.xrandr_output, "DP-0")
        self.assertEqual(config.desktop_width, 3840)
        self.assertEqual(config.desktop_height, 1080)
        self.assertEqual(config.offset_b, (0, 0))
        self.assertEqual(config.offset_a, (1920, 0))
        self.assertEqual(config.target_hz, 60)

    def test_resolve_pair_config_rejects_missing_display_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "dmd_devices.json"
            config_path.write_text(
                json.dumps(
                    {
                        "dmds": {
                            "A": {"usb_id_path": "pci-a", "xrandr_output": ""},
                            "B": {"usb_id_path": "pci-b", "xrandr_output": "DP-0"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                resolve_pair_config(config_path)


if __name__ == "__main__":
    unittest.main()
