import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dmdcontrol.runtime import pair as main_pair
from dmdcontrol.runtime.lifecycle import LutEntry
from dmdcontrol.runtime.pair import resolve_pair_config


def _parse_pair_args(args=None):
    return main_pair._build_parser().parse_args(
        ["--exposure-us", "600", *(args or [])]
    )


class MainPairConfigTests(unittest.TestCase):

    def test_resolve_pair_config_maps_b_left_and_a_right(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "dmd_devices.json"
            config_path.write_text(
                json.dumps({"dmds": {
                    "A": {"usb_id_path": "pci-a", "usb_devpath_contains": "/usb1/1-1/", "xrandr_output": "DP-2"},
                    "B": {"usb_id_path": "pci-b", "usb_devpath_contains": "/usb1/1-8/", "xrandr_output": "DP-0"},
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
                json.dumps({"dmds": {
                    "A": {"usb_id_path": "pci-a", "xrandr_output": ""},
                    "B": {"usb_id_path": "pci-b", "xrandr_output": "DP-0"},
                }}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                resolve_pair_config(config_path)

    def test_calibration_dot_recipe_accepts_essential_command_shape(self):
        args = _parse_pair_args([
            "--test", "a-calibr-square-b-dot", "--b-dot-x", "960", "--b-dot-y", "540",
            "--b-dot-radius", "40", "--preview-url", "http://127.0.0.1:8080/api/live-frame",
            "--preview-fps", "1", "--runtime-seconds", "0",
        ])
        main_pair._validate_pair_args(args)
        self.assertEqual(args.test, "a-calibr-square-b-dot")
        self.assertEqual(args.b_dot_x, 960)
        self.assertEqual(args.b_dot_y, 540)
        self.assertEqual(args.b_dot_radius, 40)

    def test_calibration_dot_recipe_rejects_static_pair_overrides(self):
        args = _parse_pair_args([
            "--test", "a-calibr-square-b-dot", "--test-a", "grid", "--b-dot-x", "960",
            "--b-dot-y", "540", "--b-dot-radius", "40",
        ])
        with self.assertRaises(SystemExit):
            main_pair._validate_pair_args(args)

    def test_kernel_static_recipe_accepts_generic_exposure_command_shape(self):
        args = _parse_pair_args([
            "--test", "a-kernel-b-static", "--test-b", "grid", "--kernel-px", "30",
            "--exposure-us", "3000", "--kernel-leader-frames", "0", "--no-kernel-blank-end-frame",
        ])
        main_pair._validate_pair_args(args)
        self.assertEqual(args.test, "a-kernel-b-static")
        self.assertEqual(args.test_b, "grid")
        self.assertEqual(args.kernel_px, 30)
        self.assertEqual(args.exposure_us, 3000)
        self.assertFalse(args.kernel_blank_end_frame)

    def test_kernel_static_recipe_accepts_essential_kernel_static_dot_command(self):
        args = _parse_pair_args([
            "--test", "a-kernel-b-static", "--test-b", "dot", "--b-dot-x", "960",
            "--b-dot-y", "540", "--b-dot-radius", "40", "--kernel-px", "201",
            "--runtime-seconds", "999",
        ])
        main_pair._validate_pair_args(args)
        self.assertEqual(args.test_b, "dot")
        self.assertEqual(args.kernel_px, 201)
        self.assertEqual(args.runtime_seconds, 999)

    def test_kernel_static_recipe_rejects_test_a_override(self):
        args = _parse_pair_args(["--test", "a-kernel-b-static", "--test-a", "grid"])
        with self.assertRaises(SystemExit):
            main_pair._validate_pair_args(args)

    def test_parser_accepts_human_visible_pair_modes(self):
        for mode in ("grid", "bands"):
            with self.subTest(mode=mode):
                args = _parse_pair_args(["--test", mode])
                main_pair._validate_pair_args(args)
                self.assertEqual(args.test, mode)

    def test_preview_args_validate_without_runtime_launch(self):
        args = _parse_pair_args([
            "--test", "grid", "--preview-url", "http://127.0.0.1:8080/api/live-frame", "--preview-fps", "1",
        ])
        main_pair._validate_pair_args(args)
        self.assertEqual(args.preview_url, "http://127.0.0.1:8080/api/live-frame")
        self.assertEqual(args.preview_fps, 1)

    def test_calibration_dot_recipe_flickers_a_square_only(self):
        from dmdcontrol.runtime import display_sequence

        args = _parse_pair_args(["--test", "a-calibr-square-b-dot", "--b-dot-x", "2", "--b-dot-y", "1", "--b-dot-radius", "1"])
        engine = SimpleNamespace(window=object())
        visible_a = np.full((main_pair.DMD_HEIGHT, main_pair.DMD_WIDTH, 3), 77, dtype=np.uint8)
        original_build = display_sequence.build_calibration_square_frame
        original_provider = display_sequence.make_calibration_square_frame_provider
        try:
            display_sequence.build_calibration_square_frame = lambda _engine, _state: visible_a
            display_sequence.make_calibration_square_frame_provider = lambda _engine, _initial_frame, **_kwargs: lambda: visible_a
            provider = display_sequence.build_paired_display_sequence(args, engine=engine, target_hz=60).provider
            first_a, first_b = provider.initial_pair()
            off_a, off_b = provider.next_pair()
            on_a, on_b = provider.next_pair()
        finally:
            display_sequence.build_calibration_square_frame = original_build
            display_sequence.make_calibration_square_frame_provider = original_provider
        np.testing.assert_array_equal(first_a, visible_a)
        np.testing.assert_array_equal(off_a, np.zeros_like(visible_a))
        np.testing.assert_array_equal(on_a, visible_a)
        np.testing.assert_array_equal(first_b, off_b)
        np.testing.assert_array_equal(off_b, on_b)

    def test_live_preview_metadata_includes_lut_timing(self):
        args = _parse_pair_args(["--test", "snake"])
        pair_config = main_pair.PairConfig(
            dmd_a=main_pair.DmdMapping(name="A", usb_id_path="pci-a", xrandr_output="DP-2"),
            dmd_b=main_pair.DmdMapping(name="B", usb_id_path="pci-b", xrandr_output="DP-0"),
            target_hz=60,
        )
        state = {
            "entries": [LutEntry(0, 600, False, 1, 7, 0, False, 0), LutEntry(8, 600, True, 1, 7, 0, False, 8)],
            "timing": {"entries_count": 2, "effective_frame_hz": 60.0, "exposure_us": 600},
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