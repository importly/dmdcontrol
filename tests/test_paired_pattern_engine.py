import unittest

import numpy as np

from paired_pattern_engine import (
    DynamicGradientPairFrameProvider,
    StaticPairFrameProvider,
    compose_pair_frame,
)


class PairedPatternEngineTests(unittest.TestCase):
    def test_compose_pair_frame_places_b_left_and_a_right(self):
        frame_a = np.full((2, 3, 3), 11, dtype=np.uint8)
        frame_b = np.full((2, 3, 3), 22, dtype=np.uint8)

        paired = compose_pair_frame(frame_a, frame_b)

        self.assertEqual(paired.shape, (2, 6, 3))
        np.testing.assert_array_equal(paired[:, :3, :], frame_b)
        np.testing.assert_array_equal(paired[:, 3:, :], frame_a)

    def test_compose_pair_frame_rejects_mismatched_shapes(self):
        frame_a = np.zeros((2, 3, 3), dtype=np.uint8)
        frame_b = np.zeros((2, 4, 3), dtype=np.uint8)

        with self.assertRaises(ValueError):
            compose_pair_frame(frame_a, frame_b)

    def test_static_pair_provider_routes_asymmetric_content(self):
        provider = StaticPairFrameProvider("checkerboard", "lines", width=16, height=8)

        first_a, first_b = provider.initial_pair()
        next_a, next_b = provider.next_pair()

        self.assertEqual(first_a.shape, (8, 16, 3))
        self.assertEqual(first_b.shape, (8, 16, 3))
        np.testing.assert_array_equal(first_a, next_a)
        np.testing.assert_array_equal(first_b, next_b)
        self.assertFalse(np.array_equal(first_a, first_b))

    def test_dynamic_gradient_provider_uses_shared_frame_index(self):
        provider = DynamicGradientPairFrameProvider(width=8, height=4)

        initial_a, initial_b = provider.initial_pair()
        next_a, next_b = provider.next_pair()

        self.assertEqual(provider.frame_index, 1)
        self.assertFalse(np.array_equal(initial_a, next_a))
        self.assertFalse(np.array_equal(initial_b, next_b))
        self.assertEqual(next_a[0, 0, 0], next_b[0, 0, 1])


if __name__ == "__main__":
    unittest.main()
