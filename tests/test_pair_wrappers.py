import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PairWrapperTests(unittest.TestCase):
    def test_run_pair_dry_run_bypasses_hardware_wake_and_xinit(self):
        script = (ROOT / "run_dmd_pair.sh").read_text(encoding="utf-8")

        dry_run_idx = script.index("Paired dry-run timing")
        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit")

        self.assertLess(dry_run_idx, wake_idx)
        self.assertLess(dry_run_idx, xinit_idx)
        self.assertIn('exec /usr/bin/python3 "$SCRIPT_DIR/main_pair.py" "$@"', script)

    def test_xinit_pair_uses_configured_target_hz_when_hz_omitted(self):
        script = (ROOT / "xinitrc_dmd_pair.sh").read_text(encoding="utf-8")

        self.assertIn('dmd_config_field "$SCRIPT_DIR" A target_hz', script)
        self.assertIn('dmd_config_field "$SCRIPT_DIR" B target_hz', script)
        self.assertIn('TARGET_HZ="${A_HZ:-${B_HZ:-60}}"', script)
        self.assertIn('DMD A and B target_hz values differ', script)

    def test_runners_source_common_shell_helpers(self):
        for name in ("run_dmd.sh", "run_calibr_square.sh", "run_dmd_pair.sh"):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('source "$SCRIPT_DIR/dmd_shell_common.sh"', script)

    def test_xinit_scripts_source_common_x11_helpers(self):
        for name in ("xinitrc_dmd.sh", "xinitrc_dmd_pair.sh"):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('source "$SCRIPT_DIR/dmd_x11_common.sh"', script)

    def test_calibration_runner_uses_shared_control_reader(self):
        script = (ROOT / "run_calibr_square.sh").read_text(encoding="utf-8")

        self.assertIn("dmd_start_calibr_square_control_reader", script)
        self.assertNotIn("stty -echo -icanon", script)

    def test_common_x11_helper_owns_raw_modelines(self):
        helper = (ROOT / "dmd_x11_common.sh").read_text(encoding="utf-8")

        self.assertIn("dmd_x11_define_raw_modes", helper)
        self.assertIn("dmd_x11_require_connected", helper)
        self.assertIn("dmd_x11_verify_pair_layout", helper)
        self.assertIn("138.6528 1920 1968 2000 2080 1080 1083 1088 1111", helper)
        self.assertIn("311.50 1920 1968 2000 2080 1080 1083 1088 1248", helper)


if __name__ == "__main__":
    unittest.main()
