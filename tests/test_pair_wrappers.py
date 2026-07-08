import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
SHELL_HELPER = SCRIPTS / "dmd_shell_common.sh"
X11_HELPER = SCRIPTS / "dmd_x11_common.sh"
XINIT_CLIENT = SCRIPTS / "dmd_xinit_client.sh"


class PairWrapperTests(unittest.TestCase):

    def test_run_dmd_routes_through_wake_hotplug_and_xinit(self):
        script = (ROOT / "run_dmd.sh").read_text(encoding="utf-8")

        wake_banner_idx = script.index("DLPC900 Initialization & DP Wake")
        wake_idx = script.index("dmd_wake_with_args")
        xinit_idx = script.index("dmd_run_xinit_python_module")

        self.assertLess(wake_banner_idx, xinit_idx)
        self.assertLess(wake_idx, xinit_idx)
        self.assertIn('dmd_run_xinit_python_module "$SCRIPT_DIR" single dmdcontrol single run -- "$@"', script)
        self.assertNotIn("dry-run", script)
        self.assertNotIn("dmd_has_flag --dry-run", script)

    def test_run_pair_routes_through_wake_hotplug_and_xinit(self):
        script = (ROOT / "run_dmd_pair.sh").read_text(encoding="utf-8")

        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit_python_module")

        self.assertLess(wake_idx, xinit_idx)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)
        self.assertIn('dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol pair run -- "$@"', script)
        self.assertNotIn("dry-run", script)
        self.assertNotIn("dmd_has_flag --dry-run", script)

    def test_common_shell_helper_execs_python_modules_with_repo_pythonpath(self):
        helper = SHELL_HELPER.read_text(encoding="utf-8")

        self.assertIn("dmd_exec_python_module() {", helper)
        self.assertNotIn("dmd_exec_python_entrypoint", helper)
        self.assertIn("dmd_run_xinit_python_module() {", helper)
        self.assertIn("__DMD_XINIT_RUN_ARGS__", helper)
        self.assertIn('"${xinit_args[@]}" -- :0 vt1', helper)
        self.assertIn("dmd_python_module() {", helper)
        self.assertIn("dmd_pythonpath() {", helper)
        self.assertIn('local repo_root="$script_dir"', helper)
        self.assertIn(
            'local pythonpath="$repo_root:/home/main/.local/lib/python3.14/site-packages"',
            helper)
        self.assertIn('exec env PYTHONPATH="$(dmd_pythonpath "$script_dir")"', helper)
        self.assertIn('/usr/bin/python3 -m "$module" "$@"', helper)

    def test_generic_xinit_client_routes_to_package_cli_after_x11_setup(self):
        client = XINIT_CLIENT.read_text(encoding="utf-8")

        self.assertIn("__DMD_XINIT_RUN_ARGS__", client)
        self.assertIn('dmd_x11_prepare_single_layout "$REPO_ROOT" "${RUN_ARGS[@]}"', client)
        self.assertIn('dmd_x11_prepare_pair_layout "$REPO_ROOT" "${RUN_ARGS[@]}"', client)
        self.assertIn(
            'dmd_exec_python_module "$REPO_ROOT" "$PYTHON_MODULE" '
            '"${PYTHON_ARGS[@]}" --monitor "$DMD_SELECTED_MONITOR_INDEX" "${RUN_ARGS[@]}"',
            client,
        )
        self.assertIn(
            'dmd_exec_python_module "$REPO_ROOT" "$PYTHON_MODULE" "${PYTHON_ARGS[@]}" "${RUN_ARGS[@]}"',
            client,
        )
        self.assertNotIn("dry-run", client)

    def test_pair_calibration_runner_routes_live_command_through_xinit(self):
        script = (ROOT / "run_dmd_pair_calibr_square.sh").read_text(encoding="utf-8")

        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit_python_module")

        self.assertLess(wake_idx, xinit_idx)
        self.assertIn('dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol pair calibrate --', script)
        self.assertIn("--test a-calibr-square-b-dot", script)
        self.assertIn('--a-calibr-square-control-file "$CONTROL_FILE"', script)
        self.assertNotIn("dry-run", script)
        self.assertNotIn("dmd_has_flag --dry-run", script)

    def test_preview_server_runner_uses_package_cli_with_default_bind(self):
        script = (ROOT / "run_dmd_preview_server.sh").read_text(encoding="utf-8")

        self.assertIn('source "$SCRIPT_DIR/scripts/dmd_shell_common.sh"', script)
        self.assertIn(
            'dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol preview serve '
            '--host 0.0.0.0 --port 8080 "$@"',
            script,
        )

    def test_generic_x11_helpers_use_fixed_60hz_modeline(self):
        helper = X11_HELPER.read_text(encoding="utf-8")

        self.assertIn('TARGET_MODE="$DMD_MODE_60"', helper)
        self.assertNotIn("dmd_parse_hz_arg", helper)
        self.assertNotIn("dmd_x11_target_mode_for_hz", helper)
        self.assertNotIn("target_hz", helper)

    def test_runners_source_common_shell_helpers(self):
        for name in (
                "run_dmd.sh",
                "run_calibr_square.sh",
                "run_dmd_pair.sh",
                "run_dmd_pair_calibr_square.sh",
        ):
            script = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn('source "$SCRIPT_DIR/scripts/dmd_shell_common.sh"', script)

    def test_generic_xinit_client_sources_common_x11_helpers(self):
        client = XINIT_CLIENT.read_text(encoding="utf-8")

        self.assertIn('source "$REPO_ROOT/scripts/dmd_x11_common.sh"', client)

    def test_calibration_runner_uses_shared_control_reader(self):
        script = (ROOT / "run_calibr_square.sh").read_text(encoding="utf-8")

        self.assertIn("dmd_start_calibr_square_control_reader", script)
        self.assertNotIn("stty -echo -icanon", script)

    def test_pair_calibration_runner_wires_recipe_and_control_file(self):
        script = (ROOT / "run_dmd_pair_calibr_square.sh").read_text(encoding="utf-8")

        self.assertIn("dmd_start_calibr_square_control_reader", script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)
        self.assertIn(
            'dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol pair calibrate --',
            script)
        self.assertIn("--test a-calibr-square-b-dot", script)
        self.assertIn('--a-calibr-square-control-file "$CONTROL_FILE"', script)
        self.assertIn("--runtime-seconds 0", script)

    def test_common_x11_helper_owns_fixed_60hz_raw_modeline(self):
        helper = X11_HELPER.read_text(encoding="utf-8")

        self.assertIn("dmd_x11_define_raw_modes", helper)
        self.assertIn("dmd_x11_require_connected", helper)
        self.assertIn("dmd_x11_verify_pair_layout", helper)
        self.assertIn("dmd_x11_prepare_single_layout", helper)
        self.assertIn("dmd_x11_prepare_pair_layout", helper)
        self.assertIn('grep -q "current 3840 x 1080"', helper)
        self.assertNotIn('grep -q "Screen 0: current 3840 x 1080"', helper)
        self.assertIn("138.6528 1920 1968 2000 2080 1080 1083 1088 1111", helper)
        self.assertNotIn("dmd_x11_target_mode_for_hz", helper)
        self.assertNotIn("DMD_MODE_120", helper)
        self.assertNotIn("311.50 1920 1968 2000 2080 1080 1083 1088 1248", helper)

    def test_common_shell_helper_does_not_parse_removed_hz_flag(self):
        helper = SHELL_HELPER.read_text(encoding="utf-8")

        self.assertNotIn("dmd_parse_hz_arg", helper)
        self.assertNotIn("--hz", helper)

    def test_camera_sync_check_runner_routes_live_capture_through_xinit(self):
        script = (ROOT / "run_camera_sync_check.sh").read_text(encoding="utf-8")

        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit_python_module")

        self.assertLess(wake_idx, xinit_idx)
        self.assertIn("camera sync-check", script)
        self.assertIn(
            'dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol camera sync-check -- "$@"',
            script)
        self.assertNotIn("xinitrc_camera_sync_check.sh", script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)
        self.assertNotIn("dry-run", script)
        self.assertNotIn("dmd_has_flag --dry-run", script)

    def test_camera_sync_sweep_runner_was_removed(self):
        self.assertFalse((ROOT / "run_camera_sync_sweep.sh").exists())

    def test_pair_capture_runner_routes_live_capture_through_xinit(self):
        script = (ROOT / "run_dmd_pair_capture.sh").read_text(encoding="utf-8")

        wake_idx = script.index("dmd_wake_configured_dmd")
        xinit_idx = script.index("dmd_run_xinit_python_module")

        self.assertLess(wake_idx, xinit_idx)
        self.assertIn("dmdcontrol camera pair-capture", script)
        self.assertIn(
            'dmd_run_xinit_python_module "$SCRIPT_DIR" pair dmdcontrol camera pair-capture -- "$@"',
            script)
        self.assertNotIn("xinitrc_dmd_pair_capture.sh", script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" A', script)
        self.assertIn('dmd_wake_configured_dmd "$SCRIPT_DIR" B', script)
        self.assertNotIn("dry-run", script)
        self.assertNotIn("dmd_has_flag --dry-run", script)

    def test_command_specific_xinit_wrappers_were_removed(self):
        self.assertFalse((SCRIPTS / "xinit").exists())

    def test_nested_scripts_lib_folder_was_removed(self):
        self.assertFalse((SCRIPTS / "lib").exists())

    def test_debug_shell_wrappers_were_removed(self):
        self.assertFalse((SCRIPTS / "debug").exists())


if __name__ == "__main__":
    unittest.main()