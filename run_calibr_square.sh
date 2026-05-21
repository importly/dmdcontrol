#!/bin/bash
# Interactive calibration-square launcher.
# This is intentionally separate from run_dmd.sh so normal DMD runs keep their
# original stdin/sudo/xinit behavior.
set -e

echo "=== DLPC900 Calibration Square ==="
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

CONTROL_FILE="$(mktemp /tmp/dmd_calibr_square_control.XXXXXX)"
CONTROL_PID=""

cleanup() {
    if [ -n "$CONTROL_PID" ]; then
        kill "$CONTROL_PID" 2>/dev/null || true
        wait "$CONTROL_PID" 2>/dev/null || true
    fi
    rm -f "$CONTROL_FILE"
}
trap cleanup EXIT

start_control_reader() {
    (
        if [ ! -r /dev/tty ]; then
            echo "Warning: /dev/tty is not readable; terminal controls are unavailable."
            exit 0
        fi

        OLD_STTY="$(stty -g < /dev/tty 2>/dev/null || true)"
        restore_tty() {
            if [ -n "$OLD_STTY" ]; then
                stty "$OLD_STTY" < /dev/tty 2>/dev/null || true
            fi
        }
        trap restore_tty EXIT INT TERM

        stty -echo -icanon min 1 time 0 < /dev/tty
        echo "Controls: W/A/S/D move, Q/E rotate, R/F resize, ESC or X exits." > /dev/tty
        echo "Square state and pixel bounds are printed by main.py after each edit." > /dev/tty

        while IFS= read -r -n 1 key < /dev/tty; do
            case "$key" in
                $'\e'|x|X)
                    printf "x" >> "$CONTROL_FILE"
                    echo "Exit requested." > /dev/tty
                    break
                    ;;
                [wWaAsSdDqQeErRfF])
                    printf "%s" "$key" | tr "[:upper:]" "[:lower:]" >> "$CONTROL_FILE"
                    ;;
            esac
        done
    ) &
    CONTROL_PID=$!
}

/usr/bin/python3 "$SCRIPT_DIR/wake_dp.py"
if [ $? -ne 0 ]; then
    echo "Error: wake_dp.py failed to run. Check USB connection to DLPC900."
    exit 1
fi

echo "Waiting 6 seconds for Xorg and GPU to detect the DP hotplug event..."
sleep 6

echo "=== Launching Interactive Calibration Square ==="
chmod +x "$SCRIPT_DIR/xinitrc_dmd.sh"
PASS_FILE="$SCRIPT_DIR/.env_pass"
if [ ! -f "$PASS_FILE" ]; then
    echo "Error: $PASS_FILE not found. Create it with: echo 'YOUR_PASSWORD' > $PASS_FILE && chmod 600 $PASS_FILE"
    exit 1
fi

start_control_reader

sudo -S xinit "$SCRIPT_DIR/xinitrc_dmd.sh" \
    --test calibr-square \
    --calibr-square-control-file "$CONTROL_FILE" \
    --runtime-seconds 0 \
    "$@" \
    -- :0 vt1 < "$PASS_FILE"

