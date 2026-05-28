import unittest

import numpy as np

from dmdcontrol.patterns.modes import PATTERN_MODES
from dmdcontrol.patterns.visual import (
    DEFAULT_COARSE_GRID_SPACING,
    DEFAULT_COARSE_GRID_THICKNESS,
    DEFAULT_COARSE_LINE_SPACING,
    DEFAULT_COARSE_LINE_THICKNESS,
    generate_coarse_grid_rgb,
    generate_coarse_lines_rgb,
)


class VisualPatternTests(unittest.TestCase):
    def test_coarse_grid_uses_human_scale_spacing_and_thick_lines(self):
        frame = generate_coarse_grid_rgb(width=240, height=180)

        self.assertEqual(DEFAULT_COARSE_GRID_SPACING, 75)
        self.assertGreaterEqual(DEFAULT_COARSE_GRID_THICKNESS, 6)
        self.assertEqual(frame.shape, (180, 240, 3))
        self.assertEqual(frame.dtype, np.uint8)
        self.assertTrue(np.isin(frame, [0, 255]).all())
        np.testing.assert_array_equal(frame[:, :, 0], frame[:, :, 1])
        np.testing.assert_array_equal(frame[:, :, 1], frame[:, :, 2])

        t = DEFAULT_COARSE_GRID_THICKNESS
        s = DEFAULT_COARSE_GRID_SPACING
        self.assertTrue(np.all(frame[:, 0:t, :] == 255))
        self.assertTrue(np.all(frame[:, s: s + t, :] == 255))
        self.assertTrue(np.all(frame[s: s + t, :, :] == 255))
        self.assertEqual(frame[t + 4, t + 4, 0], 0)

    def test_coarse_grid_can_shift_position_for_pair_distinction(self):
        frame = generate_coarse_grid_rgb(
            width=240,
            height=180,
            offset_x=DEFAULT_COARSE_GRID_SPACING // 2,
            offset_y=DEFAULT_COARSE_GRID_SPACING // 3,
        )

        self.assertEqual(frame[0, 0, 0], 0)
        self.assertEqual(frame[DEFAULT_COARSE_GRID_SPACING // 3, 0, 0], 255)
        self.assertEqual(frame[0, DEFAULT_COARSE_GRID_SPACING // 2, 0], 255)

    def test_coarse_lines_are_thick_bands_not_single_pixel_lines(self):
        vertical = generate_coarse_lines_rgb(width=240, height=180, orientation="vertical")
        horizontal = generate_coarse_lines_rgb(width=240, height=180, orientation="horizontal")

        self.assertGreaterEqual(DEFAULT_COARSE_LINE_THICKNESS, 12)
        t = DEFAULT_COARSE_LINE_THICKNESS
        s = DEFAULT_COARSE_LINE_SPACING
        self.assertTrue(np.all(vertical[:, 0:t, :] == 255))
        self.assertTrue(np.all(vertical[:, s: s + t, :] == 255))
        self.assertTrue(np.all(horizontal[0:t, :, :] == 255))
        self.assertTrue(np.all(horizontal[s: s + t, :, :] == 255))
        self.assertFalse(np.array_equal(vertical, horizontal))

    def test_single_dmd_visual_modes_are_registered(self):
        self.assertIn("coarse-grid", PATTERN_MODES)
        self.assertIn("coarse-lines", PATTERN_MODES)


if __name__ == "__main__":
    unittest.main()
