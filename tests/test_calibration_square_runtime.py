import unittest

import numpy as np

from calibration_square_runtime import (
    build_calibration_square_frame,
    format_calibration_square_state,
)
from config import BITPLANES
from pattern_modes import default_calibration_square_state


class _Engine:
    width = 64
    height = 48

    def __init__(self):
        self.patterns_seen = None

    def pack_patterns(self, patterns):
        self.patterns_seen = patterns
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :, 0] = patterns[0] * 255
        return frame


class CalibrationSquareRuntimeTests(unittest.TestCase):
    def test_build_frame_repeats_square_mask_for_all_bitplanes(self):
        engine = _Engine()
        state = default_calibration_square_state(engine.width, engine.height)

        frame = build_calibration_square_frame(engine, state)

        self.assertEqual(frame.shape, (engine.height, engine.width, 3))
        self.assertEqual(len(engine.patterns_seen), BITPLANES)
        for pattern in engine.patterns_seen:
            np.testing.assert_array_equal(pattern, engine.patterns_seen[0])
        self.assertGreater(np.count_nonzero(frame), 0)

    def test_format_state_includes_center_bounds_size_and_angle(self):
        state = default_calibration_square_state(width=64, height=48)

        text = format_calibration_square_state(state, width=64, height=48)

        self.assertIn("center=(32,24) px", text)
        self.assertIn("bounds=", text)
        self.assertIn("size=", text)
        self.assertIn("angle=0.0deg", text)


if __name__ == "__main__":
    unittest.main()
