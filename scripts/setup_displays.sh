#!/bin/bash
set -u

# gets called by python main.py for testing dmdcontrol
# based off previous shell script, parts are hardcoded to work
# with the specific setup we have in lab.

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export DISPLAY=":0"
MODE_NAME="1920x1080_60_RAW"  # defined in xorg.conf; 60.0000 Hz exactly, load-bearing for DMD sync

log()  { echo "[display] $*"; }
fail() { echo "[display] ERROR: $*" >&2; exit 1; }

OUT_A="$(python3 -c "import yaml; print(yaml.safe_load(open('$REPO_ROOT/config.yaml'))['DMD']['A']['xrandr_output'])")" \
  || fail "could not read DMD.A.xrandr_output from config.yaml"
OUT_B="$(python3 -c "import yaml; print(yaml.safe_load(open('$REPO_ROOT/config.yaml'))['DMD']['B']['xrandr_output'])")" \
  || fail "could not read DMD.B.xrandr_output from config.yaml"
log "DMD A -> $OUT_A (right), DMD B -> $OUT_B (left, primary)"

# hotplug wait
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
XLOG="/tmp/dmd_xinit_$(id -un).log"

if xrandr --query >/dev/null 2>&1; then
  log "X server already running on $DISPLAY."
else
  log "Starting X server on $DISPLAY (vt1)..."
  nohup xinit /bin/sh -c 'exec sleep infinity' -- "$DISPLAY" vt1 >"$XLOG" 2>&1 &
  for _ in $(seq 1 100); do
    xrandr --query >/dev/null 2>&1 && break
    sleep 0.1
  done
  xrandr --query >/dev/null 2>&1 \
    || fail "X server did not come up on $DISPLAY (see $XLOG; 'Only console users' there means /etc/X11/Xwrapper.config needs allowed_users=anybody)"
  log "X server is up."
fi

# outputs visible to X (X's RandR view can lag sysfs after a DP wake)
for _ in $(seq 1 50); do
  q="$(xrandr --query)"
  echo "$q" | grep -q "^$OUT_A connected" && echo "$q" | grep -q "^$OUT_B connected" && break
  sleep 0.1
done
for out in "$OUT_A" "$OUT_B"; do
  echo "$q" | grep -q "^$out connected" \
    || fail "output $out is not connected in X (connected: $(echo "$q" | grep ' connected' | cut -d' ' -f1 | tr '\n' ' '))"
done

# paired layout via nvidia-settings. NVIDIA proprietary rejects xrandr modeline
# injection; the 1920x1080_60_RAW modeline (138.6528 MHz, 2080x1111 = 60.000 Hz)
META="$OUT_B: $MODE_NAME +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}, $OUT_A: $MODE_NAME +1920+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}"
# Right after a DP wake the assignment can silently come back single-display; retry.
for _ in 1 2 3 4 5; do
  nvidia-settings -a "CurrentMetaMode=$META" >/dev/null 2>&1
  current="$(nvidia-settings -q CurrentMetaMode -t 2>/dev/null | tr -s ' \n' ' ')"
  echo "$current" | grep -q "+1920+0" && break
  sleep 1
done
echo "$current" | grep -q "+1920+0" || log "WARN: paired MetaMode not applied; CurrentMetaMode: $current"
nvidia-settings -a "Dithering=0" >/dev/null 2>&1 || log "WARN: nvidia-settings Dithering=0 failed"
xrandr --output "$OUT_B" --primary >/dev/null 2>&1 || log "WARN: could not set $OUT_B primary"
sleep 0.5  # let the layout settle; main.py validate_display() checks the result

log "Display setup done: $OUT_B left (primary), $OUT_A right."
