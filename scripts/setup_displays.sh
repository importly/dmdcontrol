#!/bin/bash
set -u

# gets called by python main.py for testing dmdcontrol
# based off previous shell script, parts are hardcoded to work
# with the specific setup we have in lab.

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DISPLAY_ID=":0"
MODE_NAME="1920x1080_60_RAW"
# 138.6528 MHz / (2080 x 1111) = 60.0000 Hz exactly -- load-bearing for DMD sync.
MODELINE="138.6528 1920 1968 2000 2080 1080 1083 1088 1111 +hsync -vsync"

log()  { echo "[display] $*"; }
fail() { echo "[display] ERROR: $*" >&2; exit 1; }

OUT_A="$(python3 -c "import yaml; print(yaml.safe_load(open('$REPO_ROOT/config.yaml'))['DMD']['A']['xrandr_output'])")" \
  || fail "could not read DMD.A.xrandr_output from config.yaml"
OUT_B="$(python3 -c "import yaml; print(yaml.safe_load(open('$REPO_ROOT/config.yaml'))['DMD']['B']['xrandr_output'])")" \
  || fail "could not read DMD.B.xrandr_output from config.yaml"
log "DMD A -> $OUT_A (right), DMD B -> $OUT_B (left, primary)"

# 1. hotplug wait
connected_dp_count() {
  local n=0 f
  for f in /sys/class/drm/*-DP-*/status; do
    [ -e "$f" ] || continue
    [ "$(cat "$f")" = "connected" ] && n=$((n + 1))
  done
  echo "$n"
}

log "Waiting for 2 connected DP outputs..."
stable=0
for _ in $(seq 1 60); do
  if [ "$(connected_dp_count)" -ge 2 ]; then
    stable=$((stable + 1))
    [ "$stable" -ge 3 ] && break
  else
    stable=0
  fi
  sleep 0.1
done
if [ "$stable" -ge 3 ]; then
  log "Both DP outputs connected."
else
  log "WARN: did not observe 2 stable DP connections; continuing anyway."
fi

# X server
xr() { xrandr --display "$DISPLAY_ID" "$@"; }
XLOG="/tmp/dmd_xinit_$(id -un).log"

if xr --query >/dev/null 2>&1; then
  log "X server already running on $DISPLAY_ID."
else
  log "Starting X server on $DISPLAY_ID (vt1)..."
  nohup xinit /bin/sh -c 'exec sleep infinity' -- "$DISPLAY_ID" vt1 >"$XLOG" 2>&1 &
  for _ in $(seq 1 100); do
    xr --query >/dev/null 2>&1 && break
    sleep 0.1
  done
  xr --query >/dev/null 2>&1 \
    || fail "X server did not come up on $DISPLAY_ID (see $XLOG; 'Only console users' there means /etc/X11/Xwrapper.config needs allowed_users=anybody)"
  log "X server is up."
fi

# outputs visible to X (X's RandR view can lag sysfs after a DP wake)
for _ in $(seq 1 50); do
  q="$(xr --query)"
  echo "$q" | grep -q "^$OUT_A connected" && echo "$q" | grep -q "^$OUT_B connected" && break
  sleep 0.1
done
for out in "$OUT_A" "$OUT_B"; do
  echo "$q" | grep -q "^$out connected" \
    || fail "output $out is not connected in X (connected: $(echo "$q" | grep ' connected' | cut -d' ' -f1 | tr '\n' ' '))"
done

# paired layout. NVIDIA proprietary rejects RandR modeline injection, so the
# 1920x1080_60_RAW modeline is baked into /etc/X11/xorg.conf.d/20-nvidia-dlpc.conf
# and the operative path is nvidia-settings CurrentMetaMode; the xrandr calls are
# best-effort (they work on nouveau).
xr --newmode "$MODE_NAME" $MODELINE 2>/dev/null || true
xr --addmode "$OUT_A" "$MODE_NAME" 2>/dev/null || true
xr --addmode "$OUT_B" "$MODE_NAME" 2>/dev/null || true
if xr --output "$OUT_B" --mode "$MODE_NAME" --pos 0x0 --primary \
      --output "$OUT_A" --mode "$MODE_NAME" --pos 1920x0 2>/dev/null; then
  log "xrandr applied paired $MODE_NAME layout."
else
  log "xrandr cannot switch by mode name (expected on NVIDIA proprietary); using nvidia-settings MetaMode."
fi

command -v nvidia-settings >/dev/null 2>&1 \
  || fail "nvidia-settings not found and xrandr could not apply $MODE_NAME"
export DISPLAY="$DISPLAY_ID"
META="$OUT_B: $MODE_NAME +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}, $OUT_A: $MODE_NAME +1920+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}"
# The assignment can be silently dropped right after a DP wake; retry until both halves are in.
for _ in 1 2 3 4 5; do
  out="$(nvidia-settings -a "CurrentMetaMode=$META" 2>&1)" || log "WARN: nvidia-settings: $(echo "$out" | tr -s ' \n' ' ')"
  current="$(nvidia-settings -q CurrentMetaMode -t 2>/dev/null | tr -s ' \n' ' ')"
  echo "$current" | grep -q "+1920+0" && break
  sleep 1
done
nvidia-settings -a "Dithering=0" >/dev/null 2>&1 || log "WARN: nvidia-settings Dithering=0 failed"
log "CurrentMetaMode: $current"
sleep 0.5  # let the layout settle; main.py validate_display() checks the result

log "Display setup done: $OUT_B left (primary), $OUT_A right."
