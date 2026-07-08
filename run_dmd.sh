#!/bin/bash
# run_dmd.sh
# Automates the sequence of waking up the DisplayPort receiver on the DLPC900 
# and launching the X11 pattern generator
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/dmd_shell_common.sh"


echo "=== DLPC900 Initialization & DP Wake ==="
dmd_wake_with_args "$SCRIPT_DIR" "$@"

dmd_wait_for_hotplug "Xorg and GPU to detect the DP hotplug event"

echo "=== Launching Pattern Engine ==="
dmd_run_xinit_python_module "$SCRIPT_DIR" single dmdcontrol single run -- "$@"
