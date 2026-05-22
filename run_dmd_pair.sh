#!/bin/bash
# run_dmd_pair.sh
# Isolated paired runner for two DLPC900 controllers on one spanning X screen.
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

ARGS=("$@")
DMD_CONFIG=""
DRY_RUN_TIMING=0
for ((i=0; i<${#ARGS[@]}; i++)); do
    case "${ARGS[i]}" in
        --dmd-config)
            if [[ $((i+1)) -lt ${#ARGS[@]} ]]; then
                DMD_CONFIG="${ARGS[i+1]}"
            fi
            ;;
        --dmd-config=*)
            DMD_CONFIG="${ARGS[i]#--dmd-config=}"
            ;;
        --dry-run-timing)
            DRY_RUN_TIMING=1
            ;;
    esac
done

CONFIG_ARGS=()
if [ -n "$DMD_CONFIG" ]; then
    CONFIG_ARGS=(--dmd-config "$DMD_CONFIG")
fi

if [ "$DRY_RUN_TIMING" = "1" ]; then
    echo "=== Paired dry-run timing (no DP wake, no X, no sudo) ==="
    exec /usr/bin/python3 "$SCRIPT_DIR/main_pair.py" "$@"
fi

echo "=== Paired DLPC900 DP Wake ==="
/usr/bin/python3 "$SCRIPT_DIR/wake_dp.py" --dmd A "${CONFIG_ARGS[@]}"
/usr/bin/python3 "$SCRIPT_DIR/wake_dp.py" --dmd B "${CONFIG_ARGS[@]}"

echo "Waiting 6 seconds for Xorg and GPU to detect both DP hotplug events..."
sleep 6

echo "=== Launching Paired Pattern Engine (via xinitrc_dmd_pair.sh wrapper) ==="
chmod +x "$SCRIPT_DIR/xinitrc_dmd_pair.sh"
PASS_FILE="$SCRIPT_DIR/.env_pass"
if [ ! -f "$PASS_FILE" ]; then
    echo "Error: $PASS_FILE not found. Create it with: echo 'YOUR_PASSWORD' > $PASS_FILE && chmod 600 $PASS_FILE"
    exit 1
fi
sudo -S xinit "$SCRIPT_DIR/xinitrc_dmd_pair.sh" "$@" -- :0 vt1 < "$PASS_FILE"
