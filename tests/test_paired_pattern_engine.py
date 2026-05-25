import unittest

import numpy as np

from visual_patterns import DEFAULT_COARSE_GRID_SPACING, generate_coarse_grid_rgb

from paired_pattern_engine import (
    CalibrationSquareDotPairFrameProvider,
    DynamicAStaticBPairFrameProvider,
    DynamicGradientPairFrameProvider,
    DynamicSnakePairFrameProvider,
    PAIR_TESTS,
    STATIC_PAIR_TESTS,
    StaticPairFrameProvider,
    compose_pair_frame,
    generate_dot_frame,
    generate_static_frame,
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
        self.assertFalse(np.array_equal(next_a, next_b))
        np.testing.assert_array_equal(next_a[:, :, 0], next_a[:, :, 1])
        np.testing.assert_array_equal(next_a[:, :, 1], next_a[:, :, 2])
        np.testing.assert_array_equal(next_b[:, :, 0], next_b[:, :, 1])
        np.testing.assert_array_equal(next_b[:, :, 1], next_b[:, :, 2])

    def test_dynamic_snake_provider_uses_grayscale_on_both_routes(self):
        provider = DynamicSnakePairFrameProvider(width=320, height=240)

        frame_a, frame_b = provider._frame_for_index(47)

        for frame in (frame_a, frame_b):
            self.assertGreater(np.count_nonzero(frame[:, :, 0]), 0)
            self.assertGreater(np.count_nonzero(frame[:, :, 1]), 0)
            self.assertGreater(np.count_nonzero(frame[:, :, 2]), 0)
            np.testing.assert_array_equal(frame[:, :, 0], frame[:, :, 1])
            np.testing.assert_array_equal(frame[:, :, 1], frame[:, :, 2])

    def test_only_colors_pair_mode_uses_route_specific_rgb_channels(self):
        for mode in STATIC_PAIR_TESTS:
            if mode == "colors":
                continue
            with self.subTest(mode=mode):
                for route in ("A", "B"):
                    frame = generate_static_frame(mode, width=320, height=240, route_label=route)
                    np.testing.assert_array_equal(frame[:, :, 0], frame[:, :, 1])
                    np.testing.assert_array_equal(frame[:, :, 1], frame[:, :, 2])

        for provider_cls in (DynamicGradientPairFrameProvider, DynamicSnakePairFrameProvider):
            with self.subTest(provider=provider_cls.__name__):
                frame_a, frame_b = provider_cls(width=320, height=240)._frame_for_index(47)
                for frame in (frame_a, frame_b):
                    np.testing.assert_array_equal(frame[:, :, 0], frame[:, :, 1])
                    np.testing.assert_array_equal(frame[:, :, 1], frame[:, :, 2])

        color_a = generate_static_frame("colors", width=320, height=240, route_label="A")
        color_b = generate_static_frame("colors", width=320, height=240, route_label="B")
        self.assertFalse(np.array_equal(color_a[:, :, 0], color_a[:, :, 1]))
        self.assertFalse(np.array_equal(color_b[:, :, 0], color_b[:, :, 1]))

    def test_generate_dot_frame_draws_circle_mask(self):
        frame = generate_dot_frame(width=7, height=7, x=3, y=3, radius=1)

        self.assertEqual(frame.shape, (7, 7, 3))
        self.assertEqual(frame.dtype, np.uint8)
        self.assertEqual(frame[3, 3, 0], 255)
        self.assertEqual(frame[2, 3, 0], 255)
        self.assertEqual(frame[3, 2, 0], 255)
        self.assertEqual(frame[4, 3, 0], 255)
        self.assertEqual(frame[3, 4, 0], 255)
        self.assertEqual(frame[2, 2, 0], 0)
        np.testing.assert_array_equal(frame[:, :, 0], frame[:, :, 1])
        np.testing.assert_array_equal(frame[:, :, 1], frame[:, :, 2])

    def test_generate_dot_frame_draws_square_and_inverts(self):
        frame = generate_dot_frame(
            width=5,
            height=5,
            x=2,
            y=2,
            radius=1,
            shape="square",
            invert=True,
        )

        self.assertEqual(frame[2, 2, 0], 0)
        self.assertEqual(frame[1, 1, 0], 0)
        self.assertEqual(frame[0, 0, 0], 255)

    def test_calibration_dot_provider_keeps_b_static_while_a_changes(self):
        frames_a = [
            np.full((3, 4, 3), 11, dtype=np.uint8),
            np.full((3, 4, 3), 33, dtype=np.uint8),
        ]
        calls = {"count": 0}

        def next_a():
            index = min(calls["count"], len(frames_a) - 1)
            calls["count"] += 1
            return frames_a[index]

        frame_b = generate_dot_frame(width=4, height=3, x=1, y=1, radius=1)
        provider = CalibrationSquareDotPairFrameProvider(next_a, frame_b)

        initial_a, initial_b = provider.initial_pair()
        next_frame_a, next_frame_b = provider.next_pair()

        np.testing.assert_array_equal(initial_a, frames_a[0])
        np.testing.assert_array_equal(next_frame_a, frames_a[1])
        self.assertIs(initial_b, frame_b)
        self.assertIs(next_frame_b, frame_b)

    def test_dynamic_a_static_b_provider_does_not_consume_a_for_initial_pair(self):
        initial_a = np.full((3, 4, 3), 7, dtype=np.uint8)
        frames_a = [
            np.full((3, 4, 3), 11, dtype=np.uint8),
            np.full((3, 4, 3), 33, dtype=np.uint8),
        ]
        calls = {"count": 0}

        def next_a():
            frame = frames_a[calls["count"]]
            calls["count"] += 1
            return frame

        frame_b = np.full((3, 4, 3), 22, dtype=np.uint8)
        provider = DynamicAStaticBPairFrameProvider(
            next_a,
            frame_b,
            initial_frame_a=initial_a,
        )

        first_a, first_b = provider.initial_pair()
        next_frame_a, next_frame_b = provider.next_pair()

        np.testing.assert_array_equal(first_a, initial_a)
        np.testing.assert_array_equal(next_frame_a, frames_a[0])
        self.assertEqual(calls["count"], 1)
        self.assertIs(first_b, frame_b)
        self.assertIs(next_frame_b, frame_b)

    def test_generate_static_frame_exposes_b_route_frame(self):
        frame = generate_static_frame("lines", width=8, height=4, route_label="B")

        self.assertEqual(frame.shape, (4, 8, 3))
        self.assertEqual(frame.dtype, np.uint8)
        self.assertGreater(frame[:, :, 1].sum(), 0)

    def test_generate_static_frame_exposes_dot_frame(self):
        frame = generate_static_frame(
            "dot",
            width=7,
            height=7,
            route_label="B",
            dot_x=3,
            dot_y=3,
            dot_radius=1,
        )

        self.assertEqual(frame.shape, (7, 7, 3))
        self.assertEqual(frame[3, 3, 0], 255)
        self.assertEqual(frame[2, 2, 0], 0)
        self.assertEqual(frame[0, 0, 0], 0)
        np.testing.assert_array_equal(
            frame,
            generate_dot_frame(width=7, height=7, x=3, y=3, radius=1),
        )

    def test_coarse_visual_modes_are_static_pair_choices(self):
        self.assertIn("coarse-grid", STATIC_PAIR_TESTS)
        self.assertIn("coarse-lines", STATIC_PAIR_TESTS)
        self.assertIn("coarse-grid", PAIR_TESTS)
        self.assertIn("coarse-lines", PAIR_TESTS)

    def test_coarse_grid_pair_frames_differ_visibly_without_color(self):
        provider = StaticPairFrameProvider("coarse-grid", "coarse-grid", width=320, height=240)

        frame_a, frame_b = provider.initial_pair()

        self.assertFalse(np.array_equal(frame_a, frame_b))
        self.assertGreater(np.count_nonzero(frame_a != frame_b), 320 * 240 * 3 * 0.08)
        np.testing.assert_array_equal(frame_a[:, :, 0], frame_a[:, :, 1])
        np.testing.assert_array_equal(frame_a[:, :, 1], frame_a[:, :, 2])
        np.testing.assert_array_equal(frame_b[:, :, 0], frame_b[:, :, 1])
        np.testing.assert_array_equal(frame_b[:, :, 1], frame_b[:, :, 2])

    def test_coarse_lines_pair_frames_use_different_large_orientations(self):
        frame_a = generate_static_frame("coarse-lines", width=320, height=240, route_label="A")
        frame_b = generate_static_frame("coarse-lines", width=320, height=240, route_label="B")

        self.assertFalse(np.array_equal(frame_a, frame_b))
        self.assertGreater(np.count_nonzero(frame_a != frame_b), 320 * 240 * 3 * 0.12)

    def test_route_markers_do_not_add_artificial_outer_border(self):
        frame = generate_static_frame("coarse-grid", width=1920, height=1080, route_label="B")
        expected_grid = generate_coarse_grid_rgb(
            width=1920,
            height=1080,
            offset_x=DEFAULT_COARSE_GRID_SPACING // 2,
            offset_y=DEFAULT_COARSE_GRID_SPACING // 2,
        )

        np.testing.assert_array_equal(frame[0, :, :], expected_grid[0, :, :])
        np.testing.assert_array_equal(frame[-1, :, :], expected_grid[-1, :, :])
        np.testing.assert_array_equal(frame[:, 0, :], expected_grid[:, 0, :])
        np.testing.assert_array_equal(frame[:, -1, :], expected_grid[:, -1, :])

        marker_area = frame[-240:, :240, :]
        self.assertGreater(np.count_nonzero(marker_area), 100 * 100 * 3)


if __name__ == "__main__":
    unittest.main()
