#!/usr/bin/env bash
# USB-only DLPC900 solid flood launcher.
#
# This intentionally does NOT use DisplayPort, Xorg, xinit, GLFW, or the
# calibration-square runtime. It only runs flood_white_usb.py against the
# currently connected DLPC900 USB controller.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

exec "$PYTHON_BIN" "$SCRIPT_DIR/flood_white_usb.py" "$@"