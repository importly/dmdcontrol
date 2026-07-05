#!/bin/bash
# Shared X11/NVIDIA layout helpers for DMD runner scripts.

DMD_MODE_60="1920x1080_60_RAW"

dmd_x11_define_raw_modes() {
    local output

    # 138.6528 MHz gives 138_652_800 / (2080 * 1111) = 60.0000 Hz exactly.
    xrandr --newmode "$DMD_MODE_60" 138.6528 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync \
        || echo "[WARN] --newmode $DMD_MODE_60 failed (likely already exists or NVIDIA rejected RandR modeline injection)"

    for output in "$@"; do
        xrandr --addmode "$output" "$DMD_MODE_60" || echo "[WARN] --addmode $DMD_MODE_60 on $output failed"
    done
}

dmd_x11_first_connected_output() {
    xrandr 2>/dev/null | grep ' connected' | grep -oE '^[A-Za-z0-9\-]+' | head -n1
}

dmd_x11_require_connected() {
    local output="$1"
    local label="$2"

    if ! xrandr --query 2>/dev/null | grep -q "^$output connected"; then
        echo "[ERROR] Configured $label output '$output' is not connected."
        echo "[ERROR] Connected outputs:"
        xrandr --query 2>/dev/null | grep ' connected' || true
        exit 1
    fi
}

dmd_x11_apply_single_mode() {
    local output="$1"
    local target_mode="$2"

    if xrandr --output "$output" --mode "$target_mode" 2>/dev/null; then
        echo "[OK] xrandr applied $target_mode on $output."
    else
        echo "[INFO] xrandr cannot switch by mode name (expected on NVIDIA proprietary)."
        echo "[INFO] Validating NVIDIA MetaMode state..."
        local current_mm
        current_mm="$(nvidia-settings -q CurrentMetaMode -t 2>/dev/null || true)"
        if echo "$current_mm" | grep -q "$target_mode"; then
            echo "[OK] NVIDIA MetaMode active: $target_mode (via xorg.conf.d/20-nvidia-dlpc.conf)."
        else
            echo "[ERROR] Neither xrandr nor NVIDIA MetaMode reports $target_mode active."
            echo "[ERROR] Current MetaMode: ${current_mm:-<unavailable>}"
            echo "[ERROR] DLPC900 needs exactly 60.000 Hz (138.6528 MHz pclk). CEA-861 60Hz (60.019 Hz) will cause forced-swap abort."
            echo "[ERROR] Verify /etc/X11/xorg.conf.d/20-nvidia-dlpc.conf MetaModes line includes \"$target_mode +0+0\"."
            exit 1
        fi
    fi
}

dmd_x11_force_single_rgb() {
    local output="$1"
    local target_mode="$2"

    nvidia-settings -a "CurrentMetaMode=${output}: ${target_mode} +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}" 2>/dev/null || true
    nvidia-settings -a "Dithering=0" 2>/dev/null || true
    xrandr --output "$output" --set "Broadcast RGB" "Full" 2>/dev/null || true
    xrandr --output "$output" --set "max bpc" 8 2>/dev/null || true
}

dmd_x11_apply_pair_mode() {
    local output_b="$1"
    local output_a="$2"
    local target_mode="$3"

    if xrandr --output "$output_b" --mode "$target_mode" --pos 0x0 --primary \
              --output "$output_a" --mode "$target_mode" --pos 1920x0 2>/dev/null; then
        echo "[OK] xrandr applied paired $target_mode layout."
    else
        echo "[INFO] xrandr cannot switch by mode name (expected on NVIDIA proprietary)."
    fi

    local meta_mode
    meta_mode="${output_b}: ${target_mode} +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}, ${output_a}: ${target_mode} +1920+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}"
    nvidia-settings -a "CurrentMetaMode=${meta_mode}" 2>/dev/null || true
    nvidia-settings -a "Dithering=0" 2>/dev/null || true

    local current_mm
    current_mm="$(nvidia-settings -q CurrentMetaMode -t 2>/dev/null || true)"
    if echo "$current_mm" | grep -q "$output_b" \
        && echo "$current_mm" | grep -q "$output_a" \
        && echo "$current_mm" | grep -q "$target_mode" \
        && echo "$current_mm" | grep -q "+1920+0"; then
        echo "[OK] NVIDIA CurrentMetaMode includes paired layout."
    else
        echo "[WARN] NVIDIA CurrentMetaMode did not confirm the paired custom MetaMode."
        echo "[WARN] CurrentMetaMode: ${current_mm:-<unavailable>}"
    fi
}

dmd_x11_verify_pair_layout() {
    local output_b="$1"
    local output_a="$2"

    if ! xrandr --query | grep -q "current 3840 x 1080"; then
        echo "[ERROR] X screen is not 3840x1080."
        exit 1
    fi
    if ! xrandr --query | grep -q "^$output_b connected primary 1920x1080+0+0"; then
        echo "[ERROR] B output is not primary at 1920x1080+0+0."
        exit 1
    fi
    if ! xrandr --query | grep -q "^$output_a connected 1920x1080+1920+0"; then
        echo "[ERROR] A output is not at 1920x1080+1920+0."
        exit 1
    fi
}

dmd_x11_prepare_single_layout() {
    local repo_root="$1"
    shift

    DMD_SELECTED_MONITOR_INDEX=0

    local args=("$@")
    local dmd_name=""
    local i
    for ((i=0; i<${#args[@]}; i++)); do
        case "${args[i]}" in
            --dmd)
                if [[ $((i+1)) -lt ${#args[@]} ]]; then
                    dmd_name="${args[i+1]}"
                fi
                ;;
            --dmd=*)
                dmd_name="${args[i]#--dmd=}"
                ;;
        esac
    done

    dmd_parse_dmd_config_arg "$@"

    local dp_output=""
    if [ -n "$dmd_name" ]; then
        dp_output="$(dmd_config_field "$repo_root" "$dmd_name" xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"
        local monitor_from_config
        monitor_from_config="$(dmd_config_field "$repo_root" "$dmd_name" glfw_monitor_index "${DMD_CONFIG_FIELD_ARGS[@]}")"
        if [ -n "$monitor_from_config" ]; then
            DMD_SELECTED_MONITOR_INDEX="$monitor_from_config"
        fi
        if [ -z "$dp_output" ]; then
            echo "[ERROR] DMD $dmd_name has no xrandr_output configured."
            echo "[ERROR] Set xrandr_output in dmd_devices.json before using --dmd so USB and DisplayPort mapping is explicit."
            exit 1
        fi
        dmd_x11_require_connected "$dp_output" "DMD $dmd_name"
    else
        dp_output="$(dmd_x11_first_connected_output)"
        if [ -z "$dp_output" ]; then
            echo "[ERROR] No connected display output found via xrandr!"
            exit 1
        fi
    fi

    echo "Detected display output: $dp_output"

    dmd_x11_define_raw_modes "$dp_output"
    TARGET_MODE="$DMD_MODE_60"

    echo "Applying custom modeline: $TARGET_MODE"
    dmd_x11_apply_single_mode "$dp_output" "$TARGET_MODE"
    dmd_x11_force_single_rgb "$dp_output" "$TARGET_MODE"

    sleep 1

    echo "--- xrandr verification ---"
    xrandr --query 2>/dev/null | grep -A 1 "^$dp_output" | head -3
}

dmd_x11_prepare_pair_layout() {
    local repo_root="$1"
    shift

    dmd_parse_dmd_config_arg "$@"

    local a_output
    local b_output
    a_output="$(dmd_config_field "$repo_root" A xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"
    b_output="$(dmd_config_field "$repo_root" B xrandr_output "${DMD_CONFIG_FIELD_ARGS[@]}")"

    if [ -z "$a_output" ] || [ -z "$b_output" ]; then
        echo "[ERROR] DMD A and B must both define xrandr_output in dmd_devices.json."
        exit 1
    fi

    dmd_x11_require_connected "$b_output" "B"
    dmd_x11_require_connected "$a_output" "A"

    echo "Pair outputs: B=$b_output at +0+0, A=$a_output at +1920+0"

    dmd_x11_define_raw_modes "$b_output" "$a_output"
    TARGET_MODE="$DMD_MODE_60"

    echo "Applying paired custom modeline: $TARGET_MODE"
    dmd_x11_apply_pair_mode "$b_output" "$a_output" "$TARGET_MODE"

    echo "--- xrandr verification ---"
    xrandr --query
    dmd_x11_verify_pair_layout "$b_output" "$a_output"
}
