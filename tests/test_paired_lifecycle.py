import unittest

from dmdcontrol.runtime.lifecycle import load_pattern_sequence, start_loaded_pattern_sequences


class _FakeDlpc:
    def __init__(self, name):
        self.name = name
        self.calls = []

    def get_hardware_status(self):
        self.calls.append(("get_hardware_status",))
        return 0

    def set_pattern_lut_definition(self, entries):
        self.calls.append(("set_pattern_lut_definition", tuple(entries)))

    def set_pattern_lut_config(self, num_entries, repeat=True):
        self.calls.append(("set_pattern_lut_config", num_entries, repeat))

    def start_pattern_display(self, mode):
        self.calls.append(("start_pattern_display", mode))

    def get_display_mode(self):
        return 2, None

    def get_main_status(self):
        return {
            "sequencer_running": True,
            "external_source_locked": True,
            "port1_syncs_valid": True,
        }


class PairedLifecycleTests(unittest.TestCase):
    def test_load_pattern_sequence_does_not_start_sequencer(self):
        dlpc = _FakeDlpc("A")

        load_pattern_sequence(dlpc, entries=[(0, 100, True, 1, 7, 0, False, 0)])

        self.assertIn(("set_pattern_lut_config", 1, True), dlpc.calls)
        self.assertNotIn(("start_pattern_display", 2), dlpc.calls)

    def test_start_loaded_pattern_sequences_starts_both_controllers(self):
        dlpc_a = _FakeDlpc("A")
        dlpc_b = _FakeDlpc("B")

        start_loaded_pattern_sequences(dlpc_a, dlpc_b)

        self.assertEqual(dlpc_a.calls.count(("start_pattern_display", 2)), 1)
        self.assertEqual(dlpc_b.calls.count(("start_pattern_display", 2)), 1)


if __name__ == "__main__":
    unittest.main()
