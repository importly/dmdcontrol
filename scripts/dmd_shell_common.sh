#!/bin/bash
# Shared helpers for DMD runner scripts.

dmd_has_flag() {
    local flag="$1"
    shift
    local arg
    for arg in "$@"; do
        if [ "$arg" = "$flag" ]; then
            return 0
        fi
    done
    return 1
}

dmd_parse_dmd_config_arg() {
    DMD_CONFIG=""
    DMD_CONFIG_ARGS=()
    DMD_CONFIG_FIELD_ARGS=()

    local args=("$@")
    local i
    for ((i=0; i<${#args[@]}; i++)); do
        case "${args[i]}" in
            --dmd-config)
                if [[ $((i+1)) -lt ${#args[@]} ]]; then
                    DMD_CONFIG="${args[i+1]}"
                fi
                ;;
            --dmd-config=*)
                DMD_CONFIG="${args[i]#--dmd-config=}"
                ;;
        esac
    done

    if [ -n "$DMD_CONFIG" ]; then
        DMD_CONFIG_ARGS=(--dmd-config "$DMD_CONFIG")
        DMD_CONFIG_FIELD_ARGS=(--config "$DMD_CONFIG")
    fi
}

dmd_require_pass_file() {
    local pass_file="$1"
    if [ ! -f "$pass_file" ]; then
        echo "Error: $pass_file not found. Create it with: echo 'YOUR_PASSWORD' > $pass_file && chmod 600 $pass_file"
        exit 1
    fi
}

dmd_wake_with_args() {
    local script_dir="$1"
    shift
    if ! dmd_python_module "$script_dir" dmdcontrol usb wake "$@"; then
        echo "Error: dmdcontrol usb wake failed to run. Check USB connection to DLPC900."
        exit 1
    fi
}

dmd_wake_configured_dmd() {
    local script_dir="$1"
    local dmd_name="$2"
    shift 2
    if ! dmd_python_module "$script_dir" dmdcontrol usb wake --dmd "$dmd_name" "$@"; then
        echo "Error: dmdcontrol usb wake failed for DMD $dmd_name. Check USB connection and dmd_devices.json."
        exit 1
    fi
}

dmd_wake_configured_pair() {
    local script_dir="$1"
    shift
    local pid_a
    local pid_b
    local status_a=0
    local status_b=0

    dmd_wake_configured_dmd "$script_dir" A "$@" &
    pid_a=$!
    dmd_wake_configured_dmd "$script_dir" B "$@" &
    pid_b=$!

    if ! wait "$pid_a"; then
        status_a=1
    fi
    if ! wait "$pid_b"; then
        status_b=1
    fi
    if [ "$status_a" -ne 0 ] || [ "$status_b" -ne 0 ]; then
        echo "Error: one or both paired DLPC900 DisplayPort wake operations failed."
        return 1
    fi
}

dmd_connected_dp_count() {
    local count=0
    local state
    local status_file
    for status_file in /sys/class/drm/*-DP-*/status; do
        if [ ! -r "$status_file" ]; then
            continue
        fi
        state=""
        IFS= read -r state < "$status_file" || true
        if [ "$state" = "connected" ]; then
            count=$((count + 1))
        fi
    done
    printf '%s\n' "$count"
}

dmd_wait_for_hotplug() {
    local label="${1:-Xorg and GPU to detect the DP hotplug event}"
    local required_dp_count="${2:-1}"
    local max_attempts=60
    local stable_required=3
    local stable_count=0
    local connected_count=0
    local attempt

    echo "Waiting up to 6 seconds for $label..."
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        connected_count="$(dmd_connected_dp_count)"
        if [ "$connected_count" -ge "$required_dp_count" ]; then
            stable_count=$((stable_count + 1))
            if [ "$stable_count" -ge "$stable_required" ]; then
                echo "Detected $connected_count connected DisplayPort output(s); continuing early."
                return 0
            fi
        else
            stable_count=0
        fi
        sleep 0.1
    done

    echo "[WARN] DisplayPort readiness was not observable in sysfs; continuing after the 6-second fallback."
}

dmd_run_xinit_python_module() {
    local script_dir="$1"
    local layout="$2"
    local module="$3"
    shift 3
    local xinitrc="$script_dir/scripts/dmd_xinit_client.sh"
    local xinit_args=()
    local saw_separator=0

    while [ "$#" -gt 0 ]; do
        if [ "$1" = "--" ]; then
            xinit_args+=("__DMD_XINIT_RUN_ARGS__")
            shift
            saw_separator=1
            break
        fi
        xinit_args+=("$1")
        shift
    done

    if [ "$saw_separator" -ne 1 ]; then
        echo "[ERROR] dmd_run_xinit_python_module requires '--' before runner arguments."
        exit 1
    fi
    xinit_args+=("$@")

    chmod +x "$xinitrc"
    local pass_file="$script_dir/.env_pass"
    dmd_require_pass_file "$pass_file"
    sudo -S xinit "$xinitrc" "$layout" "$module" "${xinit_args[@]}" -- :0 vt1 < "$pass_file"
}

dmd_config_field() {
    local script_dir="$1"
    local dmd_name="$2"
    local field="$3"
    shift 3
    dmd_python_module "$script_dir" dmdcontrol config show --dmd "$dmd_name" "$@" --field "$field"
}

dmd_pythonpath() {
    local script_dir="$1"
    local repo_root="$script_dir"
    local pythonpath="$repo_root:/home/main/.local/lib/python3.14/site-packages"
    if [ -n "${PYTHONPATH:-}" ]; then
        pythonpath="$pythonpath:$PYTHONPATH"
    fi
    echo "$pythonpath"
}

dmd_python_module() {
    local script_dir="$1"
    local module="$2"
    shift 2
    env PYTHONPATH="$(dmd_pythonpath "$script_dir")" /usr/bin/python3 -m "$module" "$@"
}

dmd_exec_python_module() {
    local script_dir="$1"
    local module="$2"
    shift 2
    exec env PYTHONPATH="$(dmd_pythonpath "$script_dir")" /usr/bin/python3 -m "$module" "$@"
}

dmd_create_calibr_square_control_file() {
    mktemp /tmp/dmd_calibr_square_control.XXXXXX
}

dmd_start_calibr_square_control_reader() {
    local control_file="$1"
    local runtime_label="${2:-dmdcontrol}"
    (
        if [ ! -r /dev/tty ]; then
            echo "Warning: /dev/tty is not readable; terminal controls are unavailable."
            exit 0
        fi

        local old_stty
        old_stty="$(stty -g < /dev/tty 2>/dev/null || true)"
        restore_tty() {
            if [ -n "$old_stty" ]; then
                stty "$old_stty" < /dev/tty 2>/dev/null || true
            fi
        }
        trap restore_tty EXIT INT TERM

        stty -echo -icanon min 1 time 0 < /dev/tty
        echo "Controls: W/A/S/D move, Q/E rotate, R/F resize, ESC or X exits." > /dev/tty
        echo "Square state and pixel bounds are printed by $runtime_label after each edit." > /dev/tty

        local key
        while IFS= read -r -n 1 key < /dev/tty; do
            case "$key" in
                $'\e'|x|X)
                    printf "x" >> "$control_file"
                    echo "Exit requested." > /dev/tty
                    break
                    ;;
                [wWaAsSdDqQeErRfF])
                    printf "%s" "$key" | tr "[:upper:]" "[:lower:]" >> "$control_file"
                    ;;
            esac
        done
    ) &
    DMD_CALIBR_CONTROL_PID=$!
}

dmd_stop_calibr_square_control_reader() {
    local control_pid="${1:-}"
    if [ -n "$control_pid" ]; then
        kill "$control_pid" 2>/dev/null || true
        wait "$control_pid" 2>/dev/null || true
    fi
}
