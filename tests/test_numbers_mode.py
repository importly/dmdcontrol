import sys
import types
import unittest
import builtins
from unittest import mock

import numpy as np

from dmdcontrol.runtime import single
from dmdcontrol.patterns.modes import (
    NUMBER_SEQUENCE,
    build_patterns,
    generate_number_rgb,
    number_index_for_elapsed,
)


def _old_default_number_nonzero_count(number, width, height):
    digit_h = max(24, int(height * 0.78))
    digit_w = min(
        max(16, int(width * 0.46)),
        max(16, int(digit_h * 0.62)),
    )
    thickness = max(4, int(min(digit_w, digit_h) * 0.16))
    x0 = (width - digit_w) // 2
    x1 = x0 + digit_w
    y0 = (height - digit_h) // 2
    y1 = y0 + digit_h
    mid = (y0 + y1) // 2
    half_t = max(2, thickness // 2)
    segments = {
        8: ("a", "b", "c", "d", "e", "f", "g"),
    }
    boxes = {
        "a": (x0 + thickness, y0, x1 - thickness, y0 + thickness),
        "b": (x1 - thickness, y0 + thickness, x1, mid),
        "c": (x1 - thickness, mid, x1, y1 - thickness),
        "d": (x0 + thickness, y1 - thickness, x1 - thickness, y1),
        "e": (x0, mid, x0 + thickness, y1 - thickness),
        "f": (x0, y0 + thickness, x0 + thickness, mid),
        "g": (x0 + thickness, mid - half_t, x1 - thickness, mid + half_t),
    }
    mask = np.zeros((height, width), dtype=np.uint8)
    for segment in segments[number]:
        sx0, sy0, sx1, sy1 = boxes[segment]
        mask[sy0:sy1, sx0:sx1] = 1
    return int(np.count_nonzero(mask) * 3)


class NumbersModeTests(unittest.TestCase):
    def test_number_index_advances_by_exposure_and_wraps(self):
        exposure_s = 0.25

        self.assertEqual(number_index_for_elapsed(0.0, exposure_s), 0)
        self.assertEqual(number_index_for_elapsed(0.249, exposure_s), 0)
        self.assertEqual(number_index_for_elapsed(0.25, exposure_s), 1)
        self.assertEqual(number_index_for_elapsed(8 * exposure_s, exposure_s), 8)
        self.assertEqual(number_index_for_elapsed(9 * exposure_s, exposure_s), 0)

    def test_generated_number_frame_is_binary_rgb_and_digit_specific(self):
        one = generate_number_rgb(1, width=120, height=160)
        eight = generate_number_rgb(8, width=120, height=160)

        self.assertEqual(NUMBER_SEQUENCE, tuple(range(1, 10)))
        self.assertEqual(one.shape, (160, 120, 3))
        self.assertEqual(one.dtype, np.uint8)
        self.assertTrue(np.isin(one, [0, 255]).all())
        self.assertGreater(np.count_nonzero(one), 0)
        self.assertGreater(np.count_nonzero(eight), np.count_nonzero(one))

    def test_default_number_geometry_matches_legacy_width_cap(self):
        eight = generate_number_rgb(8, width=120, height=160)

        self.assertEqual(
            np.count_nonzero(eight),
            _old_default_number_nonzero_count(8, width=120, height=160),
        )

    def test_generated_number_frame_respects_requested_size(self):
        small = generate_number_rgb(5, width=300, height=200, size_px=60)
        large = generate_number_rgb(5, width=300, height=200, size_px=140)

        self.assertEqual(small.shape, (200, 300, 3))
        self.assertEqual(large.shape, (200, 300, 3))
        self.assertGreater(np.count_nonzero(large), np.count_nonzero(small))

    def test_number_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            generate_number_rgb(5, width=300, height=200, size_px=0)

    def test_invalid_number_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_number_rgb(0, width=120, height=160)

    def test_numbered_region_generator_returns_rgb_grid(self):
        from dmdcontrol.patterns.numbered_regions import generate_numbered_regions

        grid = generate_numbered_regions(120, 80, grid_cols=3, grid_rows=2)

        self.assertEqual(grid.shape, (80, 120, 3))
        self.assertEqual(grid.dtype, np.uint8)
        self.assertGreater(np.count_nonzero(grid), 0)

    def test_numbered_mode_uses_packaged_generator_not_debug_scripts(self):
        original_import = builtins.__import__

        def reject_debug_scripts(name, *args, **kwargs):
            if name == "debug_scripts" or name.startswith("debug_scripts."):
                raise AssertionError("numbered mode should not import debug_scripts")
            return original_import(name, *args, **kwargs)

        engine = mock.Mock()
        engine.rgb_to_binary_patterns.return_value = "packed"

        with mock.patch.object(builtins, "__import__", side_effect=reject_debug_scripts):
            label, patterns, dynamic_kind = build_patterns(engine, "numbered")

        self.assertEqual(label, "Numbered Regions (6x4 grid)")
        self.assertEqual(patterns, "packed")
        self.assertIsNone(dynamic_kind)

    def test_dry_run_warns_when_number_size_is_ignored(self):
        args = single._build_parser().parse_args(
            ["--dry-run-timing", "--test", "checkerboard", "--numbers-size-px", "80"]
        )

        with mock.patch.object(single.logger, "warning") as warning:
            single._dry_run_timing(args)

        warning.assert_any_call("[DRY RUN] --numbers-size-px is only used with --test numbers.")

    def test_live_run_warns_when_number_size_is_ignored(self):
        engine = mock.Mock()
        engine.width = 1920
        engine.height = 1080
        engine.generate_solid.return_value = "solid"
        engine.pack_patterns.return_value = "black-frame"
        dlpc = mock.Mock()
        fake_engine_module = types.SimpleNamespace(PatternEngine=mock.Mock(return_value=engine))
        fake_dlpc_module = types.SimpleNamespace(DLPC900=mock.Mock(return_value=dlpc))

        with (
            mock.patch.dict(
                sys.modules,
                {
                    "glfw": mock.Mock(),
                    "dmdcontrol.patterns.engine": fake_engine_module,
                    "dmdcontrol.hardware.dlpc900": fake_dlpc_module,
                },
            ),
            mock.patch.object(single, "build_patterns", return_value=("Static Checkerboard", "patterns", None)),
            mock.patch.object(
                single,
                "configure_dlpc900_for_video_pattern",
                side_effect=RuntimeError("stop after warning"),
            ),
            mock.patch.object(single.logger, "warning") as warning,
        ):
            result = single.main(["--test", "checkerboard", "--numbers-size-px", "80"])

        self.assertEqual(result, 1)
        warning.assert_any_call("--numbers-size-px is only used with --test numbers; ignoring it.")


if __name__ == "__main__":
    unittest.main()
