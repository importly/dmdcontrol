# dmdcontrol

DLPC900 1080p Video Pattern Mode runtime. Drives a TI DLP6500 / DLP9000 evaluation module over USB HID with DisplayPort as the pattern source, then plays back 24 bit-planes per VSYNC frame.

## Run

Production (Linux + Xorg + DLPC900 attached):

```bash
./run_dmd.sh [flags]
```

Wraps `wake_dp.py` -> `xinit xinitrc_dmd.sh` -> `python main.py`. Requires root for `xinit`/`sudo` pieces.

Direct (skip the X11 wrapper, useful for debugging on dev host):

```bash
python main.py [flags]
```

## Common examples

```bash
./run_dmd.sh --test checkerboard
./run_dmd.sh --test snake --runtime-seconds 300
./run_dmd.sh --hz 60 -v --seq-utilization 0.70 --test checkerboard --runtime-seconds 1200
./run_dmd.sh --hz 60 -v --seq-utilization 0.7 --test snake --runtime-seconds 1200 --trig2-frame-zero
sudo ./run_dmd.sh --test clock
./run_dmd.sh --trigger --test 2x2          # spacebar fires the pattern
./run_dmd.sh --capture out.mp4 --test gradient
```

## Flags

| Flag | Type / values | Default | Purpose |
|------|---------------|---------|---------|
| `--hz` | `60`, `120` | `60` | Target VSYNC frame rate. 120 Hz is experimental and requires the source to actually deliver 120 Hz. |
| `--monitor` | int | `0` | GLFW monitor index for the fullscreen window. |
| `--test` | `checkerboard`, `ordering`, `numbered`, `single-pixel`, `2x2`, `lines`, `colors`, `snake`, `clock`, `gradient` | `checkerboard` | Diagnostic pattern. See table below. |
| `--trigger` | flag | off | Software trigger mode. Renders black until you press space; one press shows the pattern frame. ESC exits. |
| `--runtime-seconds` | int | `60` | Total wall-clock runtime for the render loop. |
| `--wake-dp` | flag | off | Send the DP-receiver wakeup packet from inside `main.py` (in addition to `wake_dp.py`). |
| `--dual-pixel` | flag | off | Force dual-pixel P1-P2 parallel input mode. Default is single-pixel P1. |
| `--seq-utilization` | float in `(0, 1]` | `0.90` | Fraction of the safe per-frame budget used by the LUT. Lower = more idle headroom = more robust against forced-swap aborts. |
| `--trig2-frame-zero` | flag | off | Emit `TRIG_OUT_2` only on bitplane 0 (one pulse per frame). Default emits per bitplane. |
| `--abort-recover-cooldown` | float seconds | `8.0` | Minimum gap between automatic re-arm attempts when the watchdog sees a sequencer abort. |
| `--no-auto-recover-abort` | flag | off | Disable automatic re-arm. Watchdog will log the abort but not act. |
| `--capture` | path to `.mp4` | none | Save the packed frames being sent to the DP output (requires `opencv-python`). |
| `-v`, `--verbose` | flag | off | Verbose logging + 2-second watchdog poll of mode/sequencer/lock/hw status. |

## Test modes

| `--test` | Description |
|----------|-------------|
| `checkerboard` | Static checkerboard. Default. |
| `ordering` | Bit-ordering sweep — verifies bitplane index -> output mapping. |
| `numbered` | 6x4 grid of numbered tiles for spatial orientation. |
| `single-pixel` | 1x1 checkerboard (creates optical diffraction with lasers). |
| `2x2` | 2x2 checkerboard. Use this to disambiguate 1:1 mapping from diffraction. |
| `lines` | Alternating 1-pixel lines. |
| `colors` | Cycles pure R / G / B every 0.5 s. |
| `snake` | High-speed randomly moving snake. Tests dynamic refresh + trigger stability. |
| `clock` | Massive microsecond clock. Visual stutter / latency check. |
| `gradient` | Temporal duty-cycle gradient. |

`--trigger` only supports patterns with a static frame (anything except `snake` / `clock`). Dynamic modes fall back to `checkerboard` when used with `--trigger`.

## Standalone tools

```bash
python wake_dp.py                      # send DP-receiver wakeup only
python debug_scripts/usb_sanity.py     # USB connectivity smoke test
```

## Layout

```
main.py             CLI parsing + orchestration
config.py           Shared timing constants (BITPLANES, SAFE_MARGIN_US, ...)
dlpc_lifecycle.py   Configure mode 2, build LUT, arm sequencer, verify state
runtime_loop.py     Render loop + watchdog + auto-recover
pattern_modes.py    Registry of --test names -> pattern builders
pattern_engine.py   GLFW + OpenGL renderer, frame packing, dynamic frames
dlpc900_hid.py      DLPC900 USB HID driver (current)
logger.py           Centralized logger
wake_dp.py          DisplayPort-receiver wakeup helper
run_dmd.sh          Top-level launcher
xinitrc_dmd.sh      X session wrapper (xrandr modeset + python launch)
debug_scripts/      usb_sanity, debug_numbered_regions
context/            Notes (DP/X11 quirks, optical diffraction, sync)
documentation/      DLPC900 / DLPT028 / DLPU018J PDFs + extracted text
```

## Help

```bash
python main.py --help
```
