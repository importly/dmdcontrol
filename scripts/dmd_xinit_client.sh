#!/bin/bash
# Generic client run by xinit for all hardware launchers.
#
# Public run_*.sh scripts do the visible orchestration: dry-run handling,
# DLPC900 DisplayPort wake, hotplug wait, and the exact Python command to run.
# xinit still needs a client script inside the new X server; this file is that
# single client. It prepares either the single-DMD or paired-DMD X layout, then
# execs the Python package command passed by the public runner.
set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$REPO_ROOT/scripts/dmd_shell_common.sh"
source "$REPO_ROOT/scripts/dmd_x11_common.sh"

if [ "$#" -lt 4 ]; then
    echo "[ERROR] Usage: dmd_xinit_client.sh <single|pair> <python-module> <python-args...> __DMD_XINIT_RUN_ARGS__ <run-args...>"
    exit 1
fi

LAYOUT="$1"
PYTHON_MODULE="$2"
shift 2

PYTHON_ARGS=()
SAW_RUN_ARGS_MARKER=0
while [ "$#" -gt 0 ]; do
    if [ "$1" = "__DMD_XINIT_RUN_ARGS__" ]; then
        shift
        SAW_RUN_ARGS_MARKER=1
        break
    fi
    PYTHON_ARGS+=("$1")
    shift
done

if [ "$SAW_RUN_ARGS_MARKER" -ne 1 ]; then
    echo "[ERROR] Missing __DMD_XINIT_RUN_ARGS__ separator."
    exit 1
fi

if [ "${#PYTHON_ARGS[@]}" -eq 0 ]; then
    echo "[ERROR] Missing Python command before __DMD_XINIT_RUN_ARGS__."
    exit 1
fi

RUN_ARGS=("$@")

echo "=== dmd_xinit_client: Configuring $LAYOUT display layout ==="
sleep 1

case "$LAYOUT" in
    single)
        dmd_x11_prepare_single_layout "$REPO_ROOT" "${RUN_ARGS[@]}"
        echo "=== Launching $PYTHON_MODULE ${PYTHON_ARGS[*]} ==="
        dmd_exec_python_module "$REPO_ROOT" "$PYTHON_MODULE" "${PYTHON_ARGS[@]}" --monitor "$DMD_SELECTED_MONITOR_INDEX" "${RUN_ARGS[@]}"
        ;;
    pair)
        dmd_x11_prepare_pair_layout "$REPO_ROOT" "${RUN_ARGS[@]}"
        echo "=== Launching $PYTHON_MODULE ${PYTHON_ARGS[*]} ==="
        dmd_exec_python_module "$REPO_ROOT" "$PYTHON_MODULE" "${PYTHON_ARGS[@]}" "${RUN_ARGS[@]}"
        ;;
    *)
        echo "[ERROR] Unknown xinit layout '$LAYOUT'. Expected 'single' or 'pair'."
        exit 1
        ;;
esac
