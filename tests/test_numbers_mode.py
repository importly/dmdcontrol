import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from dmdcontrol.runtime import single
from dmdcontrol.patterns.modes import (
    PATTERN_NAMES,
    build_patterns,
    generate_decimal_number_rgb,
)

class NumbersModeTests(unittest.TestCase):

    def test_decimal_count_label_frame_is_binary_rgb_and_digit_specific(self):
        one = generate_decimal_number_rgb(1, width=120, height=160)
        eight = generate_decimal_number_rgb(8, width=120, height=160)

        self.assertEqual(one.shape, (160, 120, 3))
        self.assertEqual(one.dtype, np.uint8)
        self.assertTrue(np.isin(one, [0, 255]).all())
        self.assertGreater(np.count_nonzero(one), 0)
        self.assertGreater(np.count_nonzero(eight), np.count_nonzero(one))

    def test_decimal_count_label_frame_respects_requested_size(self):
        small = generate_decimal_number_rgb(5, width=300, height=200, size_px=60)
        large = generate_decimal_number_rgb(5, width=300, height=200, size_px=140)

        self.assertEqual(small.shape, (200, 300, 3))
        self.assertEqual(large.shape, (200, 300, 3))
        self.assertGreater(np.count_nonzero(large), np.count_nonzero(small))

    def test_decimal_count_label_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            generate_decimal_number_rgb(5, width=300, height=200, size_px=0)

    def test_decimal_count_label_rejects_negative_values(self):
        with self.assertRaises(ValueError):
            generate_decimal_number_rgb(-1, width=120, height=160)

    def test_numbered_region_static_mode_was_removed(self):
        repo_root = Path(__file__).resolve().parents[1]

        self.assertNotIn("numbered", PATTERN_NAMES)
        self.assertFalse((repo_root / "dmdcontrol" / "patterns" / "numbered_regions.py").exists())
        with self.assertRaises(KeyError):
            build_patterns(mock.Mock(), "numbered")

    def test_legacy_single_modes_were_removed(self):
        self.assertEqual(
            PATTERN_NAMES,
            [
                "checkerboard",
                "grid",
                "bands",
                "calibr-square",
                "snake",
                "clock",
                "kernel",
            ],
        )
        for removed_mode in (
            "ordering",
            "single-pixel",
            "2x2",
            "lines",
            "colors",
            "coarse-grid",
            "coarse-lines",
            "numbers",
            "gradient",
        ):
            with self.subTest(removed_mode=removed_mode):
                with self.assertRaises(SystemExit):
                    single._build_parser().parse_args(
                        ["--dry-run-timing", "--test", removed_mode])

    def test_single_runtime_rejects_removed_numbers_size_option(self):
        with self.assertRaises(SystemExit):
            single._build_parser().parse_args(
                ["--dry-run-timing", "--test", "checkerboard", "--numbers-size-px", "80"])


if __name__ == "__main__":
    unittest.main()
