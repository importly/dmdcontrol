#!/bin/bash
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/dmd_shell_common.sh"

dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol usb discover "$@"
