import math
import unittest

from dmdcontrol.runtime.lifecycle import build_lut_entries, compute_trigger_out_2_timing


class DryRunDLPC:
    def get_display_dimensions(self):
        return None


class TriggerTimingTests(unittest.TestCase):
    def test_default_delay_is_zero_percent_of_exposure(self):
        timing = compute_trigger_out_2_timing(exposure_us=3000)

        self.assertEqual(timing["channel"], "TRIG_OUT_2")
        self.assertEqual(timing["edge"], "rising")
        self.assertEqual(timing["delay_fraction"], 0.0)
        self.assertEqual(timing["rising_delay_us"], 0)
        self.assertEqual(timing["falling_delay_us"], 20)
        self.assertEqual(timing["delay_basis"], "exposure_us")

    def test_sixty_hz_full_bitplane_lut_runs_at_1440_triggers_per_second(self):
        entries, timing = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
            trig2_frame_zero=False,
            entries_count=24,
        )

        self.assertEqual(len(entries), 24)
        self.assertEqual(timing["trig2_mode"], "per_bitplane")
        self.assertEqual(timing["effective_binary_rate_hz"], 1440.0)
        self.assertEqual(timing["exposure_us"], 615)

    def test_falling_edge_preserves_minimum_twenty_us_pulse(self):
        timing = compute_trigger_out_2_timing(exposure_us=615)

        self.assertEqual(timing["rising_delay_us"], 0)
        self.assertEqual(timing["falling_delay_us"], 20)

    def test_zero_fraction_keeps_existing_behavior_shape(self):
        timing = compute_trigger_out_2_timing(exposure_us=615, delay_fraction=0.0)

        self.assertEqual(timing["rising_delay_us"], 0)
        self.assertEqual(timing["falling_delay_us"], 20)

    def test_rejects_non_finite_delay_fraction(self):
        for value in (math.inf, -math.inf, math.nan):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "delay_fraction must be finite"):
                    compute_trigger_out_2_timing(exposure_us=615, delay_fraction=value)

    def test_rejects_negative_delay_fraction(self):
        with self.assertRaises(ValueError):
            compute_trigger_out_2_timing(exposure_us=3000, delay_fraction=-0.1)

    def test_rejects_delay_fraction_with_rising_delay_outside_signed_int16(self):
        with self.assertRaisesRegex(ValueError, "rising_delay_us .* signed int16"):
            compute_trigger_out_2_timing(exposure_us=615, delay_fraction=54.0)

    def test_rejects_delay_fraction_when_minimum_pulse_exceeds_signed_int16(self):
        with self.assertRaisesRegex(ValueError, "falling_delay_us .* signed int16"):
            compute_trigger_out_2_timing(exposure_us=615, delay_fraction=53.27)

    def test_build_lut_entries_dark_time_reduces_exposure(self):
        entries, timing = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
            dark_time_us=400,
        )
        self.assertEqual(len(entries), 24)
        # Baseline exposure without dark time is ~615.
        # With 400us dark time, exposure should be reduced by 400.
        self.assertLess(timing["exposure_us"], 615)
        self.assertAlmostEqual(timing["exposure_us"], 615 - 400, delta=10)
        # Check that dark_time_us is embedded correctly into each LUT entry (index 5)
        for entry in entries:
            self.assertEqual(entry[5], 400)

    def test_build_lut_entries_dark_time_zero_matches_default(self):
        entries_default, timing_default = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
        )
        entries_zero, timing_zero = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
            dark_time_us=0,
        )
        self.assertEqual(entries_default, entries_zero)
        self.assertEqual(timing_default, timing_zero)

    def test_build_lut_entries_custom_entries_count(self):
        entries, timing = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
            entries_count=5,
        )
        self.assertEqual(len(entries), 5)
        # With only 5 entries instead of 24, each has more time in the 1/60s frame
        self.assertGreater(timing["exposure_us"], 615)
        # Segment is roughly 14750 / 5 = 2950
        self.assertAlmostEqual(timing["exposure_us"], 2950, delta=10)


if __name__ == "__main__":
    unittest.main()
