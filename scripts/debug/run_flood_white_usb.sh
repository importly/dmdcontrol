#!/usr/bin/env bash
# USB-only DLPC900 solid flood launcher.
#
# This intentionally does NOT use DisplayPort, Xorg, xinit, GLFW, or the
# calibration-square runtime. It only runs dmdcontrol flood against the
# currently connected DLPC900 USB controller.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$REPO_ROOT/scripts/lib/dmd_shell_common.sh"

dmd_exec_python_module "$REPO_ROOT" dmdcontrol flood run "$@"
