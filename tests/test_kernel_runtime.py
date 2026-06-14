import unittest

import numpy as np

from dmdcontrol.patterns.kernel import (
    KernelFrameProvider,
    build_kernel_frames,
    compute_kernel_lut_override,
    generate_kernel_masks,
)


class _Engine:

    def __init__(self, width=12, height=12):
        self.width = width
        self.height = height

    def pack_patterns(self, binary_images):
        r = np.zeros((self.height, self.width), dtype=np.uint8)
        g = np.zeros((self.height, self.width), dtype=np.uint8)
        b = np.zeros((self.height, self.width), dtype=np.uint8)
        for i in range(8):
            g |= binary_images[i] << i
            r |= binary_images[i + 8] << i
            b |= binary_images[i + 16] << i
        return np.stack([r, g, b], axis=-1)


class KernelRuntimeTests(unittest.TestCase):

    def test_compute_kernel_lut_override_clamps_to_bitplane_count(self):
        entries, exposure_us = compute_kernel_lut_override(
            enabled=True,
            kernel_exposure_us=3000,
            target_hz=60,
            sequence_utilization=0.9,
        )

        self.assertEqual(entries, 4)
        self.assertEqual(exposure_us, 3000)

    def test_compute_kernel_lut_override_counts_dark_time_in_slot_budget(self):
        entries, exposure_us = compute_kernel_lut_override(
            enabled=True,
            kernel_exposure_us=5000,
            target_hz=60,
            sequence_utilization=0.9,
            dark_time_us=5000,
        )

        self.assertEqual(entries, 1)
        self.assertEqual(exposure_us, 5000)

    def test_compute_kernel_lut_override_returns_none_when_disabled(self):
        self.assertEqual(
            compute_kernel_lut_override(
                enabled=False,
                kernel_exposure_us=3000,
                target_hz=60,
                sequence_utilization=0.9,
            ),
            (None,
             None),
        )

    def test_generate_kernel_masks_builds_512_centered_masks(self):
        masks = generate_kernel_masks(width=12, height=12, kernel_px=6)

        self.assertEqual(len(masks), 512)
        self.assertEqual(masks[0].sum(), 0)
        self.assertEqual(masks[1].sum(), 4)
        self.assertEqual(masks[511].sum(), 36)

    def test_build_kernel_frames_includes_leaders_and_optional_blank(self):
        engine = _Engine()

        frames, metadata = build_kernel_frames(
            engine,
            kernel_px=6,
            slots_per_frame=24,
            leader_frames=2,
            blank_end_frame=True,
        )

        self.assertEqual(len(frames), 25)
        self.assertEqual(metadata["leader_frames"], 2)
        self.assertEqual(metadata["payload_vsyncs"], 23)
        self.assertEqual(metadata["blank_slot_count"], 16)
        np.testing.assert_array_equal(frames[0], np.zeros((12, 12, 3), dtype=np.uint8))
        np.testing.assert_array_equal(frames[1], np.zeros((12, 12, 3), dtype=np.uint8))
        np.testing.assert_array_equal(frames[-1], np.zeros((12, 12, 3), dtype=np.uint8))

    def test_kernel_frame_provider_loops_or_holds_black_after_single_shot(self):
        frames = [
            np.full((2,
                     2,
                     3),
                    10,
                    dtype=np.uint8),
            np.full((2,
                     2,
                     3),
                    20,
                    dtype=np.uint8),
        ]
        black = np.zeros((2, 2, 3), dtype=np.uint8)

        looping = KernelFrameProvider(frames, black_frame=black)
        np.testing.assert_array_equal(looping(), frames[0])
        np.testing.assert_array_equal(looping(), frames[1])
        np.testing.assert_array_equal(looping(), frames[0])

        one_shot = KernelFrameProvider(frames, black_frame=black, single_shot=True)
        np.testing.assert_array_equal(one_shot(), frames[0])
        np.testing.assert_array_equal(one_shot(), frames[1])
        np.testing.assert_array_equal(one_shot(), black)


if __name__ == "__main__":
    unittest.main()
