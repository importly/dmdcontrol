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

if xr --query >/dev/null 2>&1; then
  log "X server already running on $DISPLAY_ID."
else
  log "Starting X server on $DISPLAY_ID (vt1)..."
  # The sleep client keeps the server alive after this script returns; the
  # server survives until reboot or an explicit kill, so repeat runs reuse it.
  nohup xinit /bin/sh -c 'exec sleep infinity' -- "$DISPLAY_ID" vt1 \
    >/tmp/dmd_xinit.log 2>&1 &
  for _ in $(seq 1 100); do
    xr --query >/dev/null 2>&1 && break
    sleep 0.1
  done
  xr --query >/dev/null 2>&1 \
    || fail "X server did not come up on $DISPLAY_ID (see /tmp/dmd_xinit.log)"
  log "X server is up."
fi

# modeline + paired layout
for out in "$OUT_A" "$OUT_B"; do
  xr --query | grep -q "^$out connected" || fail "output $out is not connected"
done

xr --newmode "$MODE_NAME" $MODELINE 2>/dev/null || true # already defined -> fine
xr --addmode "$OUT_A" "$MODE_NAME" 2>/dev/null || true
xr --addmode "$OUT_B" "$MODE_NAME" 2>/dev/null || true

xr --output "$OUT_B" --mode "$MODE_NAME" --pos 0x0 --primary \
   --output "$OUT_A" --mode "$MODE_NAME" --pos 1920x0 \
  || fail "xrandr layout failed"

if command -v nvidia-settings >/dev/null 2>&1; then
  DISPLAY="$DISPLAY_ID" nvidia-settings -a \
    "CurrentMetaMode=$OUT_B: $MODE_NAME +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}, $OUT_A: $MODE_NAME +1920+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}" \
    >/dev/null || log "WARN: nvidia-settings MetaMode failed"
  DISPLAY="$DISPLAY_ID" nvidia-settings -a "Dithering=0" >/dev/null \
    || log "WARN: nvidia-settings Dithering=0 failed"
else
  log "WARN: nvidia-settings not found; skipping MetaMode/dithering setup."
fi
sleep 0.5  # let the layout settle; main.py validate_display() checks the result

log "Display setup done: $OUT_B left (primary), $OUT_A right."
