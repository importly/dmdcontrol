#!/bin/bash
# run_dmd_pair.sh
# Isolated paired runner for two DLPC900 controllers on one spanning X screen.
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/dmd_shell_common.sh"

dmd_parse_dmd_config_arg "$@"

if dmd_has_flag --dry-run-timing "$@"; then
    echo "=== Paired dry-run timing (no DP wake, no X, no sudo) ==="
    dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair run "$@"
fi

echo "=== Paired DLPC900 DP Wake ==="
dmd_wake_configured_dmd "$SCRIPT_DIR" A "${DMD_CONFIG_ARGS[@]}"
dmd_wake_configured_dmd "$SCRIPT_DIR" B "${DMD_CONFIG_ARGS[@]}"

dmd_wait_for_hotplug "Xorg and GPU to detect both DP hotplug events"

echo "=== Launching Paired Pattern Engine (via xinitrc_dmd_pair.sh wrapper) ==="
dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/xinitrc_dmd_pair.sh" "$@"
