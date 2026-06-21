import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dmdcontrol.runtime import pair as main_pair
from dmdcontrol.runtime.pair import resolve_pair_config


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
                        }}),
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
                            "A": {
                                "usb_id_path": "pci-a",
                                "xrandr_output": ""},
                            "B": {
                                "usb_id_path": "pci-b",
                                "xrandr_output": "DP-0"},
                        }}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                resolve_pair_config(config_path)

    def test_dry_run_accepts_essential_calibration_dot_command_without_hardware_imports(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        rc = main_pair.main(
            [
                "--dry-run-timing",
                "--test",
                "a-calibr-square-b-dot",
                "--b-dot-x",
                "960",
                "--b-dot-y",
                "540",
                "--b-dot-radius",
                "40",
                "--preview-url",
                "http://127.0.0.1:8080/api/live-frame",
                "--preview-fps",
                "1",
                "--runtime-seconds",
                "0",
            ])

        self.assertEqual(rc, 0)
        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_calibration_dot_recipe_rejects_static_pair_overrides(self):
        with self.assertRaises(SystemExit):
            main_pair.main(
                [
                    "--dry-run-timing",
                    "--test",
                    "a-calibr-square-b-dot",
                    "--test-a",
                    "lines",
                    "--b-dot-x",
                    "960",
                    "--b-dot-y",
                    "540",
                    "--b-dot-radius",
                    "40",
                ])

    def test_dry_run_accepts_kernel_static_recipe_without_hardware_imports(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        rc = main_pair.main(
            [
                "--dry-run-timing",
                "--test",
                "a-kernel-b-static",
                "--test-b",
                "lines",
                "--kernel-px",
                "30",
                "--exposure-us",
                "3000",
                "--kernel-leader-frames",
                "0",
                "--no-kernel-blank-end-frame",
            ])

        self.assertEqual(rc, 0)
        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_dry_run_accepts_essential_kernel_static_dot_command(self):
        rc = main_pair.main(
            [
                "--dry-run-timing",
                "--test",
                "a-kernel-b-static",
                "--test-b",
                "dot",
                "--b-dot-x",
                "960",
                "--b-dot-y",
                "540",
                "--b-dot-radius",
                "40",
                "--kernel-px",
                "201",
                "--runtime-seconds",
                "999",
            ])

        self.assertEqual(rc, 0)

    def test_kernel_static_recipe_rejects_test_a_override(self):
        with self.assertRaises(SystemExit):
            main_pair.main(
                [
                    "--dry-run-timing",
                    "--test",
                    "a-kernel-b-static",
                    "--test-a",
                    "lines",
                ])

    def test_dry_run_accepts_human_visible_pair_modes_without_hardware_imports(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        for mode in ("coarse-grid", "coarse-lines"):
            with self.subTest(mode=mode):
                rc = main_pair.main(["--dry-run-timing", "--test", mode])

                self.assertEqual(rc, 0)
                self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_dry_run_accepts_preview_args_without_hardware_imports(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        rc = main_pair.main(
            [
                "--dry-run-timing",
                "--test",
                "coarse-grid",
                "--preview-url",
                "http://127.0.0.1:8080/api/live-frame",
                "--preview-fps",
                "1",
            ])

        self.assertEqual(rc, 0)
        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_calibration_dot_recipe_flickers_a_square_only(self):
        args = main_pair._build_parser().parse_args(
            [
                "--test",
                "a-calibr-square-b-dot",
                "--b-dot-x",
                "2",
                "--b-dot-y",
                "1",
                "--b-dot-radius",
                "1",
            ])
        engine = SimpleNamespace(window=object())
        visible_a = np.full((main_pair.DMD_HEIGHT, main_pair.DMD_WIDTH, 3), 77, dtype=np.uint8)
        original_build = main_pair.build_calibration_square_frame
        original_provider = main_pair.make_calibration_square_frame_provider
        try:
            main_pair.build_calibration_square_frame = lambda _engine, _state: visible_a
            main_pair.make_calibration_square_frame_provider = (
                lambda _engine, _initial_frame, **_kwargs: lambda: visible_a)

            provider = main_pair._make_runtime_pair_frame_provider(args, engine, 60)
            first_a, first_b = provider.initial_pair()
            off_a, off_b = provider.next_pair()
            on_a, on_b = provider.next_pair()
        finally:
            main_pair.build_calibration_square_frame = original_build
            main_pair.make_calibration_square_frame_provider = original_provider

        np.testing.assert_array_equal(first_a, visible_a)
        np.testing.assert_array_equal(off_a, np.zeros_like(visible_a))
        np.testing.assert_array_equal(on_a, visible_a)
        np.testing.assert_array_equal(first_b, off_b)
        np.testing.assert_array_equal(off_b, on_b)

    def test_live_preview_metadata_includes_lut_timing(self):
        args = main_pair._build_parser().parse_args(["--test", "snake"])
        pair_config = main_pair.PairConfig(
            dmd_a=main_pair.DmdMapping(name="A",
                                       usb_id_path="pci-a",
                                       xrandr_output="DP-2"),
            dmd_b=main_pair.DmdMapping(name="B",
                                       usb_id_path="pci-b",
                                       xrandr_output="DP-0"),
            target_hz=60,
        )
        state = {
            "entries": [(0,
                         600,
                         False,
                         1,
                         7,
                         0,
                         False,
                         0),
                        (8,
                         600,
                         True,
                         1,
                         7,
                         0,
                         False,
                         8)],
            "timing": {
                "entries_count": 2,
                "effective_frame_hz": 60.0,
                "exposure_us": 600},
        }

        metadata = main_pair._build_live_preview_metadata(args, pair_config, state, state)

        self.assertEqual(metadata["layout"], "pair")
        self.assertEqual(metadata["test"], "snake")
        self.assertEqual(metadata["routes"]["B"]["position"], "left")
        self.assertEqual(metadata["routes"]["A"]["position"], "right")
        self.assertEqual(metadata["lut"]["entries"][0]["plane_label"], "G0")
        self.assertEqual(metadata["lut"]["entries"][1]["plane_label"], "R0")
        self.assertEqual(metadata["lut"]["timing"]["effective_frame_hz"], 60.0)


if __name__ == "__main__":
    unittest.main()
