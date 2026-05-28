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

dmd_parse_hz_arg() {
    local fallback="$1"
    shift
    DMD_TARGET_HZ="$fallback"

    local args=("$@")
    local i
    for ((i=0; i<${#args[@]}; i++)); do
        case "${args[i]}" in
            --hz)
                if [[ $((i+1)) -lt ${#args[@]} ]]; then
                    DMD_TARGET_HZ="${args[i+1]}"
                fi
                ;;
            --hz=*)
                DMD_TARGET_HZ="${args[i]#--hz=}"
                ;;
        esac
    done
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

dmd_wait_for_hotplug() {
    local label="${1:-Xorg and GPU to detect the DP hotplug event}"
    echo "Waiting 6 seconds for $label..."
    sleep 6
}

dmd_run_xinit() {
    local script_dir="$1"
    local xinitrc="$2"
    shift 2
    chmod +x "$xinitrc"
    local pass_file="$script_dir/.env_pass"
    dmd_require_pass_file "$pass_file"
    sudo -S xinit "$xinitrc" "$@" -- :0 vt1 < "$pass_file"
}

dmd_config_field() {
    local script_dir="$1"
    local dmd_name="$2"
    local field="$3"
    shift 3
    dmd_python_module "$script_dir" dmdcontrol config show --dmd "$dmd_name" "$@" --field "$field"
}

dmd_exec_python_entrypoint() {
    local script_dir="$1"
    local entrypoint="$2"
    shift 2
    exec env PYTHONPATH="$(dmd_pythonpath "$script_dir")" \
        /usr/bin/python3 "$script_dir/compat/legacy/$entrypoint" "$@"
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
