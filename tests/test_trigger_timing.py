import unittest

from dmdcontrol.runtime.lifecycle import LutEntry, build_lut_entries, compute_trigger_out_2_timing


class DryRunDLPC:

    def get_display_dimensions(self):
        return None


class TriggerTimingTests(unittest.TestCase):

    def test_default_rising_delay_is_zero_microseconds(self):
        timing = compute_trigger_out_2_timing()

        self.assertEqual(timing["channel"], "TRIG_OUT_2")
        self.assertEqual(timing["edge"], "rising")
        self.assertEqual(timing["rising_delay_us"], 0)
        self.assertEqual(timing["falling_delay_us"], 20)
        self.assertEqual(timing["pulse_width_us"], 20)

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

    def test_lut_entry_has_named_fields_and_legacy_tuple_shape(self):
        entries, _timing = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
            entries_count=1,
            per_entry_exposure_us=4000,
        )

        entry = entries[0]

        self.assertIsInstance(entry, LutEntry)
        self.assertEqual(entry.bitplane_index, 0)
        self.assertEqual(entry.exposure_us, 4000)
        self.assertEqual(entry.clear_after, True)
        self.assertEqual(entry.bit_depth, 1)
        self.assertEqual(entry.led_select, 7)
        self.assertEqual(entry.dark_us, 0)
        self.assertEqual(entry.trig2_disabled, False)
        self.assertEqual(entry.bit_position, 0)
        self.assertEqual(entry, (0, 4000, True, 1, 7, 0, False, 0))

    def test_falling_edge_preserves_minimum_twenty_us_pulse(self):
        timing = compute_trigger_out_2_timing(rising_delay_us=15)

        self.assertEqual(timing["rising_delay_us"], 15)
        self.assertEqual(timing["falling_delay_us"], 35)

    def test_accepts_negative_twenty_microsecond_rising_delay(self):
        timing = compute_trigger_out_2_timing(rising_delay_us=-20)

        self.assertEqual(timing["rising_delay_us"], -20)
        self.assertEqual(timing["falling_delay_us"], 0)
        self.assertEqual(timing["pulse_width_us"], 20)

    def test_rejects_non_integer_rising_delay(self):
        with self.assertRaisesRegex(ValueError, "rising_delay_us must be an integer"):
            compute_trigger_out_2_timing(rising_delay_us=0.5)

    def test_rejects_rising_delay_below_dlpc900_range(self):
        with self.assertRaisesRegex(ValueError, "rising_delay_us must be between -20 and 19980"):
            compute_trigger_out_2_timing(rising_delay_us=-21)

    def test_rejects_rising_delay_when_derived_falling_delay_exceeds_dlpc900_range(self):
        with self.assertRaisesRegex(ValueError, "rising_delay_us must be between -20 and 19980"):
            compute_trigger_out_2_timing(rising_delay_us=19981)

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

    def test_build_lut_entries_rejects_negative_dark_time(self):
        with self.assertRaisesRegex(ValueError, "dark_time_us must be non-negative"):
            build_lut_entries(
                DryRunDLPC(),
                target_hz=60,
                dark_time_us=-1,
            )

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

    def test_build_lut_entries_direct_exposure_computes_entry_count_when_dynamic(self):
        entries, timing = build_lut_entries(
            DryRunDLPC(),
            target_hz=60,
            per_entry_exposure_us=4000,
            dark_time_us=250,
        )

        self.assertEqual(len(entries), 3)
        self.assertEqual(timing["entries_count"], 3)
        self.assertEqual(timing["exposure_us"], 4000)
        self.assertEqual(timing["dark_us"], 250)
        self.assertEqual(timing["effective_binary_rate_hz"], 180.0)


if __name__ == "__main__":
    unittest.main()
