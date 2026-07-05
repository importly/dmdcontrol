import unittest

import numpy as np
import pytest

from dmdcontrol.patterns.kernel import (
    KernelFrameBuild,
    KernelFrameProvider,
    KernelLutOverride,
    build_kernel_frames,
    compute_kernel_lut_override,
    generate_kernel_masks,
)
from dmdcontrol.runtime import single as single_runtime


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

    def test_single_runtime_parser_rejects_removed_hz_flag(self):
        with self.assertRaises(SystemExit):
            single_runtime._build_parser().parse_args(["--dry-run-timing", "--hz", "120"])

    def test_compute_kernel_lut_override_clamps_to_bitplane_count(self):
        override = compute_kernel_lut_override(
            enabled=True,
            exposure_us=3000,
            target_hz=60,
            sequence_utilization=0.9,
        )
        entries, exposure_us = override

        self.assertIsInstance(override, KernelLutOverride)
        self.assertEqual(override.entries_count, 4)
        self.assertEqual(override.exposure_us, 3000)
        self.assertEqual(entries, 4)
        self.assertEqual(exposure_us, 3000)

    def test_compute_kernel_lut_override_counts_dark_time_in_slot_budget(self):
        entries, exposure_us = compute_kernel_lut_override(
            enabled=True,
            exposure_us=5000,
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
                exposure_us=3000,
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

        build = build_kernel_frames(
            engine,
            kernel_px=6,
            slots_per_frame=24,
            leader_frames=2,
            blank_end_frame=True,
        )
        frames, metadata = build

        self.assertIsInstance(build, KernelFrameBuild)
        self.assertEqual(len(frames), 25)
        self.assertEqual(build.metadata["leader_frames"], 2)
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


@pytest.mark.parametrize("flag", ["--kernel-exposure-us", "--numbers-exposure-us"])
def test_single_runtime_parser_rejects_removed_exposure_flags(flag):
    with pytest.raises(SystemExit):
        single_runtime._build_parser().parse_args(["--dry-run-timing", flag, "3000"])


def test_single_runtime_kernel_uses_generic_exposure_for_lut_timing():
    args = single_runtime._build_parser().parse_args(
        [
            "--test",
            "kernel",
            "--exposure-us",
            "3000",
            "--dry-run-timing",
        ])

    assert single_runtime._compute_kernel_lut_override(args, target_hz=60) == (4, 3000)


def test_single_runtime_static_dry_run_forwards_generic_exposure(monkeypatch):
    captured = {}

    def fake_build_lut_entries(*_args, **kwargs):
        captured["entries_count"] = kwargs["entries_count"]
        captured["per_entry_exposure_us"] = kwargs["per_entry_exposure_us"]
        captured["dark_time_us"] = kwargs["dark_time_us"]
        return [(0, 4000, False, 1, 7, 250, False, 0)] * 3, {
            "exposure_us": 4000,
            "dark_us": 250,
            "total_sequence_us": 12750.0,
            "usable_frame_period_us": 14775.0,
            "idle_headroom_us": 3916.7,
            "trig2_mode": "per_bitplane",
            "effective_frame_hz": 60.0,
            "effective_binary_rate_hz": 180.0,
        }

    monkeypatch.setattr(single_runtime, "build_lut_entries", fake_build_lut_entries)
    args = single_runtime._build_parser().parse_args(
        [
            "--test",
            "checkerboard",
            "--exposure-us",
            "4000",
            "--dark-time-us",
            "250",
            "--dry-run-timing",
        ])

    single_runtime._dry_run_timing(args)

    assert captured == {
        "entries_count": None,
        "per_entry_exposure_us": 4000,
        "dark_time_us": 250,
    }


def test_single_runtime_warns_that_dark_time_is_unreliable_in_video_pattern_mode(caplog):
    args = single_runtime._build_parser().parse_args(
        ["--test", "checkerboard", "--dark-time-us", "250", "--dry-run-timing"])

    single_runtime._warn_dark_time_video_pattern_mode(args)

    assert "--dark-time-us" in caplog.text
    assert "does not work as expected with DLPC900 Video Pattern Mode" in caplog.text


def test_single_runtime_rejects_removed_numbers_mode():
    with pytest.raises(SystemExit):
        single_runtime._build_parser().parse_args(
            [
                "--test",
                "numbers",
                "--exposure-us",
                "3000",
                "--dry-run-timing",
            ])


if __name__ == "__main__":
    unittest.main()
