import unittest

import numpy as np

from dmdcontrol.patterns.modes import (
    apply_calibration_square_commands,
    calibration_square_bounds,
    default_calibration_square_state,
    generate_calibration_square_mask,
)


class CalibrationSquareModeTests(unittest.TestCase):

    def test_default_state_is_centered_and_sized_from_surface(self):
        state = default_calibration_square_state(width=100, height=80)

        self.assertEqual(state.x, 50.0)
        self.assertEqual(state.y, 40.0)
        self.assertEqual(state.size, 20.0)
        self.assertEqual(state.angle_deg, 0.0)

    def test_keyboard_commands_move_rotate_resize_and_clamp(self):
        state = default_calibration_square_state(width=100, height=80)

        updated = apply_calibration_square_commands(
            state,
            "wdqr",
            width=100,
            height=80,
            move_px=10,
            rotation_deg=5,
            size_step_px=8,
        )

        self.assertEqual(updated.x, 60.0)
        self.assertEqual(updated.y, 30.0)
        self.assertEqual(updated.size, 28.0)
        self.assertEqual(updated.angle_deg, 355.0)

        clamped = apply_calibration_square_commands(
            updated,
            "aaaaafffff",
            width=100,
            height=80,
            move_px=50,
            size_step_px=10,
        )

        self.assertEqual(clamped.x, 0.0)
        self.assertEqual(clamped.size, 4.0)

    def test_bounds_report_clipped_pixel_extent(self):
        state = default_calibration_square_state(width=100, height=80)

        bounds = calibration_square_bounds(state, width=100, height=80)

        self.assertEqual(bounds, (40, 30, 60, 50))

    def test_generated_square_mask_is_binary_and_rotatable(self):
        square = generate_calibration_square_mask(
            width=80,
            height=80,
            center_x=40,
            center_y=40,
            size_px=20,
            angle_deg=0,
        )
        diamond = generate_calibration_square_mask(
            width=80,
            height=80,
            center_x=40,
            center_y=40,
            size_px=20,
            angle_deg=45,
        )

        self.assertEqual(square.shape, (80, 80))
        self.assertEqual(square.dtype, np.uint8)
        self.assertTrue(np.isin(square, [0, 1]).all())
        self.assertGreater(np.count_nonzero(square), 0)
        self.assertFalse(np.array_equal(square, diamond))


if __name__ == "__main__":
    unittest.main()
