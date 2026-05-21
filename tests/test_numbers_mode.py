import unittest

import numpy as np

from pattern_modes import (
    NUMBER_SEQUENCE,
    generate_number_rgb,
    number_index_for_elapsed,
)


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

    def test_invalid_number_is_rejected(self):
        with self.assertRaises(ValueError):
            generate_number_rgb(0, width=120, height=160)


if __name__ == "__main__":
    unittest.main()
