#!/bin/bash
# run_dmd.sh
# Automates the sequence of waking up the DisplayPort receiver on the DLPC900 
# and launching the X11 pattern generator
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/lib/dmd_shell_common.sh"

if dmd_has_flag --dry-run-timing "$@"; then
    echo "=== Single dry-run timing (no DP wake, no X, no sudo) ==="
    dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol single run "$@"
    exit 0
fi

echo "=== DLPC900 Initialization & DP Wake ==="
dmd_wake_with_args "$SCRIPT_DIR" "$@"

dmd_wait_for_hotplug "Xorg and GPU to detect the DP hotplug event"

echo "=== Launching Pattern Engine (via scripts/xinit/xinitrc_dmd.sh wrapper) ==="
# The xinitrc wrapper handles: fixed 1920x1080 mode set -> python launch
dmd_run_xinit "$SCRIPT_DIR" "$SCRIPT_DIR/scripts/xinit/xinitrc_dmd.sh" "$@"
