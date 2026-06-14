import unittest

import numpy as np

from dmdcontrol.runtime.single import _select_post_arm_prime_frame


class PostArmPrimeFrameTests(unittest.TestCase):

    def test_kernel_prime_skips_black_leader_frames(self):
        leader0 = np.zeros((1, 1, 3), dtype=np.uint8)
        leader1 = np.zeros((1, 1, 3), dtype=np.uint8)
        first_payload = np.full((1, 1, 3), 7, dtype=np.uint8)
        frames = [leader0, leader1, first_payload]

        selected = _select_post_arm_prime_frame(
            initial_frame=leader0,
            dynamic_kind="kernel",
            kernel_frames=frames,
            kernel_leader_frames=2,
        )

        self.assertIs(selected, first_payload)

    def test_non_kernel_prime_uses_initial_frame(self):
        initial = np.full((1, 1, 3), 3, dtype=np.uint8)

        selected = _select_post_arm_prime_frame(
            initial_frame=initial,
            dynamic_kind=None,
            kernel_frames=None,
            kernel_leader_frames=0,
        )

        self.assertIs(selected, initial)


if __name__ == "__main__":
    unittest.main()
