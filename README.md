# dmdcontrol

DLPC900 1080p Video Pattern Mode runtime. Drives a TI DLP6500 / DLP9000 evaluation module over USB HID with DisplayPort as the pattern source, then plays back up to 24 bit-planes per VSYNC frame. This is a incomplete README.

## Prerequisites

- Linux + Xorg (tested on Fedora 43, kernel 7.0.8, X.Org 21.1.22)
- NVIDIA proprietary driver (akmod-nvidia via RPM Fusion). The nouveau driver works but lacks GL acceleration. Custom modeline injection via `xrandr --newmode` is rejected by NVIDIA proprietary, so the modeline must be baked into `/etc/X11/xorg.conf.d/20-nvidia-dlpc.conf`.
- DLPC900 EVM connected via USB (HID interface 0) and DisplayPort
- Python 3.13+, PyOpenGL, GLFW, `opencv-python` (only for `--capture`)
- Custom 1920x1080 @ 60.000 Hz exact modeline (pclk 138.6528 MHz, htotal 2080, vtotal 1111). CEA-861 60Hz (actually 60.019 Hz) causes DLPC900 forced-swap abort.

### Required xorg.conf snippet

`/etc/X11/xorg.conf.d/20-nvidia-dlpc.conf` must declare:

- A `Monitor` section with the custom `ModeLine "1920x1080_60_RAW" 138.6528 1920 1968 2000 2080 1080 1083 1088 1111 +HSync -VSync`
- A `Device` section with `Option "ModeValidation" "AllowNonEdidModes, NoMaxPClkCheck, NoEdidMaxPClkCheck, NoVertRefreshCheck, NoHorizSyncCheck, NoMaxSizeCheck, NoXServerCheck, NoDFPNativeResolutionCheck, NoVesaModes, NoXServerModes, NoPredefinedModes"`
- A `Screen` section with `Option "MetaModes" "1920x1080_60_RAW +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}"`

`xinitrc_dmd.sh` detects when xrandr cannot switch to the custom mode by name (expected on NVIDIA proprietary) and validates the active MetaMode via `nvidia-settings -q CurrentMetaMode` instead. It only aborts if neither path applied the target mode.

## Run

Production (Linux + Xorg + DLPC900 attached):

```bash
./run_dmd.sh [flags]
```

Wraps `wake_dp.py` -> `xinit xinitrc_dmd.sh` -> `python main.py`. Requires root for `xinit`.

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
./run_dmd.sh --test clock
./run_dmd.sh --trigger --test 2x2          # spacebar fires the pattern
./run_dmd.sh --capture out.mp4 --test gradient

# 3x3 convolution kernel rotation (512 patterns, eye-visible at 14000 us)
./run_dmd.sh --test kernel --kernel-px 900 --kernel-exposure-us 14000 --runtime-seconds 999

# Same, fast (full 1440 Hz binary rate, 24 bitplanes per VSYNC)
./run_dmd.sh --test kernel --kernel-px 900 --runtime-seconds 60
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
| `--kernel-px` | int (multiple of 3) | `30` | Total kernel side length in pixels for `--test kernel`. Single-cell size = `kernel-px / 3`. |
| `--kernel-single-shot` | flag | off | Display each kernel for exactly one bitplane fire then advance. Implies dynamic frame buffer cycling. |
| `--kernel-blank-end-frame` | flag | off | Force the last bitplane of each VSYNC to be blank (debug aid for trigger alignment). |
| `--kernel-exposure-us` | int µs | auto | Override per-kernel exposure. Reduces entries-per-VSYNC and slows the cycle. Cap is one VSYNC (~14773 µs at 90% utilization). |
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
| `kernel` | 3x3 convolution kernel rotation — cycles through 512 kernel masks. Configurable via `--kernel-px`, `--kernel-exposure-us`, `--kernel-single-shot`, `--kernel-blank-end-frame`. |

`--trigger` only supports patterns with a static frame (anything except `snake` / `clock` / `kernel`). Dynamic modes fall back to `checkerboard` when used with `--trigger`.

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

## Trigger output behavior

DLPC900 in Video Pattern Mode drives two GPIO trigger outputs. Their on-scope behavior surprises people, so:

- **TRIG_OUT_1 is a frame-active GATE, not a momentary pulse.** It asserts at the start of the first bitplane of a frame and deasserts after the last bitplane ends. With `dark=0` (the default) and high utilization (e.g. 24 entries × 615 µs = 14760 µs active out of 16667 µs VSYNC), TRIG_OUT_1 is HIGH ~88% of the time. `rising_delay_us` / `falling_delay_us` only configure leading/trailing edge skew relative to frame boundaries — not pulse width.
- **TRIG_OUT_2 fires per bitplane** (or once per frame on bitplane 0 with `--trig2-frame-zero`). Default pulse width = 20 µs. With 24 entries × 615 µs and dark=0, you get 24 pulses spaced 615 µs apart, then a ~1907 µs idle gap, then the next burst. **Scope auto-Hz reads ~1.63 kHz** because it windows over the dense burst region (1/615 µs ≈ 1626 Hz). **Pulses per second over a 1.000 s counter gate = 1440** (24 × 60 frames). Both numbers are correct; they describe different things.
- For uniform 1440 Hz output (every pulse exactly 694 µs apart), you would need `dark=79` µs to push the per-entry period from 615 to 694, eliminating the VSYNC idle gap. The current `INTER_PATTERN_DARK_US = 0` in `config.py` is intentional — it maximizes integration time per bitplane.

### Hardware status bit interpretation

The DLPC900 hardware status register (read via cmd 0x1A0A) exposes status flags. Two are easy to misread:

- **Bit 6 ("Sequence Abort Status Flag" per DLPU018J Table 2-21)** behaves in our setup as a state-machine flag rather than a fault indicator. It is set after every `start_pattern_display(0)` (Pattern Stop) and persists until the next `start_pattern_display(2)` completes a clean handoff. It is also set at boot and persists across barrel power cycles. Treat as cosmetic when `sequencer_running`, `external_source_locked`, and `port1_syncs_valid` are all true and forced-swap (bit 3) and sequence-error (bit 7) are clear. The retry loop in `dlpc_lifecycle.apply_pattern_sequence` will log a few `[arm] bit-6 latched` lines at DEBUG and then proceed.
- **Bit 7 ("Sequence Error Flag")** is the real runtime-error signal. If you see this set, investigate.

The runtime watchdog logs `hw=0x61` continuously when bit 0 (init_ok), bit 5 (reserved, commonly reads 1), and bit 6 (cosmetic ABORT) are set. That is the healthy steady-state pattern.

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
xinitrc_dmd.sh      X session wrapper (xrandr modeset + MetaMode validation + python launch)
sync_dmd.sh         rsync local -> lab box (bash)
sync_dmd.ps1        rsync local -> lab box (PowerShell)
debug_scripts/      usb_sanity, debug_numbered_regions
context/            Notes (DP/X11 quirks, optical diffraction, sync)
documentation/      DLPC900 / DLPT028 / DLPU018J PDFs + extracted text
```

## Help

```bash
python main.py --help
```
