import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHELL_HELPER = SCRIPTS / "lib" / "dmd_shell_common.sh"
X11_HELPER = SCRIPTS / "lib" / "dmd_x11_common.sh"
XINIT = SCRIPTS / "xinit"


class PairWrapperTests(unittest.TestCase):
    def test_run_pair_dry_run_bypasses_hardware_wake_and_xinit(self):
        script = (ROOT / "run_dmd_pair.sh").read_text(encoding="utf-8")

        dry_run_idx = script.index("Paired dry-run timing")
        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit")

        self.assertLess(dry_run_idx, wake_idx)
        self.assertLess(dry_run_idx, xinit_idx)
        self.assertIn('dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair run "$@"', script)

    def test_common_shell_helper_execs_python_modules_with_repo_pythonpath(self):
        helper = SHELL_HELPER.read_text(encoding="utf-8")

        self.assertIn("dmd_exec_python_module() {", helper)
        self.assertIn("dmd_python_module() {", helper)
        self.assertIn("dmd_pythonpath() {", helper)
        self.assertIn('local repo_root="$script_dir"', helper)
        self.assertIn('local pythonpath="$repo_root:/home/main/.local/lib/python3.14/site-packages"', helper)
        self.assertIn('exec env PYTHONPATH="$(dmd_pythonpath "$script_dir")"', helper)
        self.assertIn('/usr/bin/python3 -m "$module" "$@"', helper)

    def test_xinit_wrappers_route_to_package_cli_after_x11_setup(self):
        single = (XINIT / "xinitrc_dmd.sh").read_text(encoding="utf-8")
        pair = (XINIT / "xinitrc_dmd_pair.sh").read_text(encoding="utf-8")

        self.assertIn(
            'dmd_exec_python_module "$REPO_ROOT" dmdcontrol single run --monitor "$MONITOR_INDEX" "$@"',
            single,
        )
        self.assertIn('dmd_exec_python_module "$REPO_ROOT" dmdcontrol pair run "$@"', pair)

    def test_pair_calibration_dry_run_routes_to_package_calibrate_command(self):
        script = (ROOT / "run_dmd_pair_calibr_square.sh").read_text(encoding="utf-8")

        self.assertIn("Paired calibration dry-run timing", script)
        self.assertIn(
            'dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair calibrate "$@"',
            script,
        )

    def test_preview_server_runner_uses_package_cli_with_default_bind(self):
        script = (ROOT / "run_dmd_preview_server.sh").read_text(encoding="utf-8")

        self.assertIn('source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"', script)
        self.assertIn(
            'dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol preview serve '
            '--host 0.0.0.0 --port 8080 "$@"',
            script,
        )

    def test_xinit_pair_uses_configured_target_hz_when_hz_omitted(self):
        script = (XINIT / "xinitrc_dmd_pair.sh").read_text(encoding="utf-8")

        self.assertIn('dmd_config_field "$REPO_ROOT" A target_hz', script)
        self.assertIn('dmd_config_field "$REPO_ROOT" B target_hz', script)
        self.assertIn('TARGET_HZ="${A_HZ:-${B_HZ:-60}}"', script)
        self.assertIn('DMD A and B target_hz values differ', script)

    def test_runners_source_common_shell_helpers(self):
        for name in (
            "run_dmd.sh",
            "run_calibr_square.sh",
            "run_dmd_pair.sh",
            "run_dmd_pair_calibr_square.sh",
        ):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"', script)

    def test_xinit_scripts_source_common_x11_helpers(self):
        for name in ("xinitrc_dmd.sh", "xinitrc_dmd_pair.sh"):
            script = (XINIT / name).read_text(encoding="utf-8")
            self.assertIn('source "$REPO_ROOT/scripts/lib/dmd_x11_common.sh"', script)

    def test_calibration_runner_uses_shared_control_reader(self):
        script = (ROOT / "run_calibr_square.sh").read_text(encoding="utf-8")

        self.assertIn("dmd_start_calibr_square_control_reader", script)
        self.assertNotIn("stty -echo -icanon", script)

    def test_pair_calibration_runner_wires_recipe_and_control_file(self):
        script = (ROOT / "run_dmd_pair_calibr_square.sh").read_text(encoding="utf-8")

        self.assertIn("dmd_start_calibr_square_control_reader", script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)
        self.assertIn('dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/scripts/xinit/xinitrc_dmd_pair.sh"', script)
        self.assertIn("--test a-calibr-square-b-dot", script)
        self.assertIn('--a-calibr-square-control-file "$CONTROL_FILE"', script)
        self.assertIn("--runtime-seconds 0", script)

    def test_common_x11_helper_owns_raw_modelines(self):
        helper = X11_HELPER.read_text(encoding="utf-8")

        self.assertIn("dmd_x11_define_raw_modes", helper)
        self.assertIn("dmd_x11_require_connected", helper)
        self.assertIn("dmd_x11_verify_pair_layout", helper)
        self.assertIn('grep -q "current 3840 x 1080"', helper)
        self.assertNotIn('grep -q "Screen 0: current 3840 x 1080"', helper)
        self.assertIn("138.6528 1920 1968 2000 2080 1080 1083 1088 1111", helper)
        self.assertIn("311.50 1920 1968 2000 2080 1080 1083 1088 1248", helper)

    def test_camera_sync_check_runner_routes_dry_run_without_xinit(self):
        script = (ROOT / "run_camera_sync_check.sh").read_text(encoding="utf-8")

        dry_run_idx = script.index("Camera sync-check dry-run")
        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit")

        self.assertLess(dry_run_idx, wake_idx)
        self.assertLess(dry_run_idx, xinit_idx)
        self.assertIn("camera sync-check", script)
        self.assertIn("dmd_has_flag --dry-run", script)
        self.assertIn("xinitrc_camera_sync_check.sh", script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)

        dry_run_command_idx = script.index(
            'dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol camera sync-check "$@"'
        )
        dry_run_guarded_by_exit = (
            script.find("exit 0", dry_run_command_idx, wake_idx) != -1
        )
        dry_run_guarded_by_else = (
            script.find("else", dry_run_command_idx, wake_idx) != -1
            and script.find("fi", wake_idx, xinit_idx) != -1
        )
        self.assertTrue(
            dry_run_guarded_by_exit or dry_run_guarded_by_else,
            "sync-check dry-run must exit or use else before DP wake/xinit",
        )

    def test_camera_sync_check_xinit_runs_camera_module(self):
        script = (XINIT / "xinitrc_camera_sync_check.sh").read_text(encoding="utf-8")

        self.assertIn("dmdcontrol camera sync-check", script)
        self.assertIn("dmd_x11_verify_pair_layout", script)
        self.assertIn('source "$REPO_ROOT/scripts/lib/dmd_x11_common.sh"', script)

    def test_camera_sync_sweep_runner_routes_dry_run_without_xinit(self):
        script = (ROOT / "run_camera_sync_sweep.sh").read_text(encoding="utf-8")

        dry_run_idx = script.index("Camera sync-sweep dry-run")
        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit")

        self.assertLess(dry_run_idx, wake_idx)
        self.assertLess(dry_run_idx, xinit_idx)
        self.assertIn("camera sync-sweep", script)
        self.assertIn("dmd_has_flag --dry-run", script)
        self.assertIn("xinitrc_camera_sync_sweep.sh", script)

    def test_camera_sync_sweep_xinit_runs_camera_module(self):
        script = (XINIT / "xinitrc_camera_sync_sweep.sh").read_text(encoding="utf-8")

        self.assertIn("dmdcontrol camera sync-sweep", script)
        self.assertIn("dmd_x11_verify_pair_layout", script)
        self.assertIn('source "$REPO_ROOT/scripts/lib/dmd_x11_common.sh"', script)

    def test_pair_capture_runner_routes_dry_run_without_xinit(self):
        script = (ROOT / "run_dmd_pair_capture.sh").read_text(encoding="utf-8")

        dry_run_idx = script.index("Paired camera capture dry-run timing")
        dry_run_command_idx = script.index(
            'dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol camera pair-capture "$@"'
        )
        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit")

        self.assertLess(dry_run_idx, wake_idx)
        self.assertLess(dry_run_idx, xinit_idx)
        self.assertIn("dmdcontrol camera pair-capture", script)
        self.assertIn("dmd_has_flag --dry-run-timing", script)
        self.assertIn("xinitrc_dmd_pair_capture.sh", script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)

        dry_run_guarded_by_exit = (
            script.find("exit 0", dry_run_command_idx, wake_idx) != -1
        )
        dry_run_guarded_by_else = (
            script.find("else", dry_run_command_idx, wake_idx) != -1
            and script.find("fi", wake_idx, xinit_idx) != -1
        )
        self.assertTrue(
            dry_run_guarded_by_exit or dry_run_guarded_by_else,
            "pair-capture dry-run must exit or use else before DP wake/xinit",
        )

    def test_pair_capture_xinit_runs_camera_module(self):
        script = (XINIT / "xinitrc_dmd_pair_capture.sh").read_text(encoding="utf-8")

        self.assertIn("dmdcontrol camera pair-capture", script)
        self.assertIn("dmd_x11_verify_pair_layout", script)
        self.assertIn('source "$REPO_ROOT/scripts/lib/dmd_x11_common.sh"', script)


if __name__ == "__main__":
    unittest.main()
