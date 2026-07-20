import unittest

import numpy as np

from dmdcontrol.patterns.modes import generate_decimal_number_rgb


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





if __name__ == "__main__":
    unittest.main()
