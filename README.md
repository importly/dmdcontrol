# dmdcontrol

Pair-only DLPC900 1080p Video Pattern Mode runtime. It drives labeled DMDs A and B over USB HID, presents one
3840x1080 DisplayPort source spanning both 1920x1080 devices, and optionally coordinates that paired output with a
DVXplorer camera for sync checks and captures.

## Prerequisites

- Linux + Xorg (tested on Fedora 43, kernel 7.0.8, X.Org 21.1.22)
- NVIDIA proprietary driver (akmod-nvidia via RPM Fusion). The nouveau driver works but lacks GL acceleration. Custom
  modeline injection via `xrandr --newmode` is rejected by NVIDIA proprietary, so the modeline must be baked into
  `/etc/X11/xorg.conf.d/20-nvidia-dlpc.conf`.
- Two DLPC900 EVMs connected through their configured USB HID and DisplayPort paths
- Python 3.13+, PyOpenGL, and GLFW
- The exact 1920x1080 @ 60.000 Hz modeline on both outputs (pclk 138.6528 MHz, htotal 2080, vtotal 1111). CEA-861
  60 Hz (actually 60.019 Hz) causes DLPC900 forced-swap abort.

### Required xorg.conf snippet

`/etc/X11/xorg.conf.d/20-nvidia-dlpc.conf` must declare:

- A `Monitor` section with the custom
  `ModeLine "1920x1080_60_RAW" 138.6528 1920 1968 2000 2080 1080 1083 1088 1111 +HSync -VSync`
- A `Device` section with
  `Option "ModeValidation" "AllowNonEdidModes, NoMaxPClkCheck, NoEdidMaxPClkCheck, NoVertRefreshCheck, NoHorizSyncCheck, NoMaxSizeCheck, NoXServerCheck, NoDFPNativeResolutionCheck, NoVesaModes, NoXServerModes, NoPredefinedModes"`
- A `Screen` section with
  `Option "MetaModes" "DP-0: 1920x1080_60_RAW +0+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}, DP-2: 1920x1080_60_RAW +1920+0 {ColorSpace=RGB, ColorRange=Full, ForceFullCompositionPipeline=On}"`

`scripts/dmd_x11_common.sh` detects when xrandr cannot switch to the custom mode by name (expected on NVIDIA
proprietary) and validates the active MetaMode via `nvidia-settings -q CurrentMetaMode` instead. It only aborts if
neither path applied the target mode.

## Command model

On the Linux DMD box, the root launchers are the production orchestration entrypoints. Every hardware launcher prepares
the configured A/B pair: DisplayPort wakeup, `xinit`, sudo/env pass-through, NVIDIA/X11 paired-layout validation, and
optional calibration terminal input. The pair-only X-stage client is `scripts/dmd_xinit_client.sh`.

```bash
./run_dmd_pair.sh --exposure-us 14000 [other flags]
./run_dmd_pair_calibr_square.sh --exposure-us 14000 [other flags]
./run_camera_sync_check.sh --exposure-us 16000 [other flags]
./run_dmd_pair_capture.sh --exposure-us 14000 [other flags]
```

For local development on Windows or any host without DMD hardware, debug the fake-backed pytest targets. Use the package CLI inside an already prepared Linux X session when driving hardware directly:

```bash
python -m pytest tests/test_camera_live_plumbing.py -q
python -m pytest tests/test_pair_lut_override.py -q
python -m dmdcontrol preview serve --host 127.0.0.1 --port 8080
python -m dmdcontrol usb discover
python -m dmdcontrol usb wake
python -m dmdcontrol config show --dmd A
```

Compatibility shims such as `compat/legacy/main.py`, `compat/legacy/main_pair.py`, and `compat/legacy/wake_dp.py` live
under `compat/legacy/`. Use `run_dmd_preview_server.sh` for the preview server default bind, or `python -m dmdcontrol`
directly for custom preview-server workflows.

## Development verification

Install the locked development dependencies and run the production-package type check plus the full
hardware-independent test suite:

```bash
uv sync --group dev
uv run basedpyright
uv run pytest -q
```

OpenCV is not required by the runtime. Install the optional accelerated notebook path with
`uv sync --group dev --extra analysis`; without it, the camera-analysis notebooks use their slower NumPy dilation
fallback.

The committed basedpyright configuration checks `dmdcontrol/` with Python 3.13 in standard mode. Research
notebooks and `server_backup/` are intentionally outside that production type-check boundary.

Import architecture keeps deferred imports at explicit boundaries only. `dmdcontrol.cli.main` imports the selected command
adapter after parsing the command, while command adapters and runtime modules use ordinary imports. Function-local imports
are reserved for optional `dv_processing`, native OpenGL construction, and the lightweight `dmdcontrol.preview` public API;
the CLI test suite audits this allowlist so module-returning lazy-loader helpers cannot creep back in.

## Essential Linux DMD workflows

Paired kernel-on-A with static dot-on-B:

```bash
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --exposure-us 14000 --runtime-seconds 999
```

Equivalent package CLI, for use only inside a prepared X session:

```bash
python -m dmdcontrol pair run --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --exposure-us 14000 --runtime-seconds 999
```

Paired calibration square on A with static dot-on-B and live preview:

```bash
./run_dmd_pair_calibr_square.sh --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --exposure-us 14000 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

Equivalent package CLI, for use only inside a prepared X session:

```bash
python -m dmdcontrol pair calibrate --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --exposure-us 14000 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

Run the preview server separately before using a `--preview-url`:

```bash
./run_dmd_preview_server.sh
# open http://127.0.0.1:8080/
```

Linux DMD verification checklist:

- `python -m dmdcontrol usb discover` sees both DLPC900 boards.
- `python -m dmdcontrol config show --dmd A` and `--dmd B` resolve the expected USB and DisplayPort mappings.
- `./run_dmd_preview_server.sh` serves `http://127.0.0.1:8080/`.
- The paired kernel shell command above starts both DMDs, shows B's dot, and runs A's kernel sequence.
- The paired calibration shell command above keeps B's dot static, shows the interactive A square, and updates
  `http://127.0.0.1:8080/api/live-frame`.

## Dual-DMD mapping

All hardware runs resolve DMD A and DMD B from `dmd_devices.json`. Inspect either labeled mapping without opening USB:

```bash
python -m dmdcontrol config show --dmd A
python -m dmdcontrol config show --dmd B
```

Each mapping binds a logical label to its udev `ID_PATH`, expected `DEVPATH` fragment, and XRandR output. Pair startup
fails closed if either USB or DisplayPort mapping is unavailable.

Current mapping:

| DMD | USB identity                    | Physical USB path | DisplayPort output |
|-----|---------------------------------|-------------------|--------------------|
| A   | `pci-0000:03:00.0-usb-0:1:1.0` | `usb1/1-1`        | `DP-2`             |
| B   | `pci-0000:03:00.0-usb-0:8:1.0` | `usb1/1-8`        | `DP-0`             |

Both controllers report serial `C900`, so mapping is by labeled USB and DisplayPort ports. It has been verified after
reboot; keep the hardware plugged into the same labeled ports.

## Paired Dual-DMD Runner

Paired mode is the only live DMD flow:

```bash
./run_dmd_pair.sh --test grid --exposure-us 14000 --runtime-seconds 300
./run_dmd_pair.sh --test bands --exposure-us 14000 --runtime-seconds 300
./run_dmd_pair.sh --test checkerboard --test-a checkerboard --test-b grid --exposure-us 14000
./run_dmd_pair.sh --test a-kernel-b-static --test-b grid --kernel-px 900 --exposure-us 14000 --runtime-seconds 999
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --exposure-us 14000 --runtime-seconds 999
./run_dmd_pair.sh --test static-images --static-image-b images/O.png --static-image-a images/T.png --static-image-size-px 1080 --exposure-us 14000 --runtime-seconds 999
./run_dmd_pair_calibr_square.sh --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --exposure-us 14000 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

`run_dmd_pair.sh` wakes both mapped controllers, starts the generic `scripts/dmd_xinit_client.sh` in paired-layout
mode, and launches `python -m dmdcontrol pair run`. The paired X layout is one X screen at `3840x1080`: B/`DP-0` is the left half at
`+0+0`, and A/`DP-2` is the right half at `+1920+0`. The runtime opens one undecorated GLFW window at `(0, 0)`, renders
B into `x=0..1919`, renders A into `x=1920..3839`, and performs one buffer swap per paired frame.

Paired launchers minimize cold-start latency without weakening the controller transition sequence:

- DMD A and B DisplayPort receivers are woken concurrently.
- Linux DRM connector state is sampled until both DisplayPort outputs are connected for three consecutive polls.
  The previous six-second wait remains the bounded fallback when connector readiness is not exposed in sysfs.
- After the shared framebuffer is live, the two independent DLPC900 controllers are prepared concurrently.
- The conservative 3 s buffer, 2 s pipeline, and 1 s VSYNC dwells are bounded stability checks over external lock,
  Port 1 sync validity, video-frozen state, and display mode. The working-reference 500 ms Video Pattern Mode
  transition guard and the block-lock workaround delays remain unchanged.

`--test static-images` loads one image for each DMD, keeps each image's aspect ratio, resizes the longest side to
`--static-image-size-px`, alpha-composites onto black, centers the result on each 1920x1080 DMD canvas, and repeats those
static frames for the full run. The B image is shown on the left output and the A image is shown on the right output.

For visual inspection through the tiny optical images, use `grid` or `bands`. They draw thick geometry and large A/B
block markers without adding an artificial outer border to the 1920x1080 DMD image.

`run_dmd_pair_calibr_square.sh` runs the paired calibration recipe with DMD A on the right showing the interactive
calibration square and DMD B on the left showing the static dot. The A square flickers every other displayed frame; the
B dot does not flicker.

Preview packed frames and individual DLPC900 bitplanes in a browser:

```bash
./run_dmd_preview_server.sh
# open http://127.0.0.1:8080/
./run_dmd_pair.sh --test grid --exposure-us 14000 --runtime-seconds 300 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

The preview server is offline by default and does not open GLFW, OpenGL, USB, or DMD hardware. `--preview-url` is opt-in
live mirroring from the paired runtime. Live posts include the configured DLPC900 LUT order and timing, so the browser
can show which packed bitplanes are being displayed during each VSYNC. The logical order is `G0..G7`, then `R0..R7`,
then `B0..B7`. Video Pattern setup explicitly selects DisplayPort/parallel RGB888 input and sets the LightCrafter
6500/9000 EVM data-channel swap to `ABC->BAC` so logical RGB maps to the DLPC900 A/B/C input pins correctly.

Dynamic paired `snake` is rendered as grayscale on both routes for bitplane inspection. If a snake segment is present,
it should be visible in the corresponding G/R/B bitplanes according to its intensity bits, not only on one color channel
for one DMD.

Both DLPC900 controllers are prepared and have matching LUTs loaded before the final sequencer start. The final
`start_pattern_display(2)` commands are issued from a tight software barrier while the paired DP stream is actively
pumping. This improves software alignment, but it is not a hard genlock guarantee on consumer GPU outputs. Measure A
`TRIG_OUT_2` and B `TRIG_OUT_2` on a scope to decide whether initial skew and long-run drift are acceptable for the
laser path.

## Additional pair examples

```bash
./run_dmd_pair.sh --test checkerboard --exposure-us 14000 --runtime-seconds 300
./run_dmd_pair.sh --test snake --exposure-us 14000 --runtime-seconds 300
./run_dmd_pair.sh -v --seq-utilization 0.70 --test grid --exposure-us 14000 --runtime-seconds 1200

# 3x3 convolution kernel rotation on A with a static dot on B
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --kernel-px 900 --exposure-us 14000 --runtime-seconds 999

# Local timing and LUT checks without hardware
python -m pytest tests/test_kernel_runtime.py tests/test_pair_lut_override.py -q
```

## Paired runtime flags

Pair launchers use the custom `1920x1080_60_RAW` modeline and fixed 60.000 Hz timing. Run
`python -m dmdcontrol pair run --help` for the complete current interface.

| Flag | Default | Purpose |
|------|---------|---------|
| `--dmd-config` | `dmd_devices.json` | Alternate A/B USB and DisplayPort mapping file. |
| `--test` | `checkerboard` | Select a paired static, dynamic, or recipe mode. |
| `--test-a` / `--test-b` | mode default | Override the A/B pattern for static paired modes. |
| `--runtime-seconds` | `60` | Total paired render-loop duration; `0` runs until the window closes. |
| `--exposure-us` | required | Per-entry DLPC900 LUT exposure in microseconds. |
| `--dark-time-us` | `0` | Programmed LUT dark time; explicit blank frames are preferred for visible off-time. |
| `--wake-dp` | off | Wake both DisplayPort receivers from inside the runtime. |
| `--dual-pixel` | off | Force P1-P2 dual-pixel input mode on both controllers. |
| `--seq-utilization` | `0.90` | Fraction of the safe VSYNC budget available to LUT entries. |
| `--trig2-frame-zero` | off | Emit `TRIG_OUT_2` only on bitplane/frame-zero anchor entries. |
| `--paired-startup-leader-vsyncs` | `16` | Non-semantic paired source frames after sequencer start; camera artifacts skip these triggers. |
| `--trigger-out-2-rising-delay-us` | `0` | `TRIG_OUT_2` rising-edge delay; valid range is -20 to 19980 µs. |
| `--kernel-px` | `30` | A-side 3x3 kernel width for `a-kernel-b-static`. |
| `--kernel-single-shot` | off | Play one A-side kernel cycle, then hold A black. |
| `--kernel-leader-frames` | `3` | Black VSYNC frames prepended to an A-side kernel cycle. |
| `--count-start` / `--count-end` | `1` / `100` | Inclusive number range for `a-count-b-static`. |
| `--count-slots-per-frame` | `auto` | Number of count labels packed into each source VSYNC. |
| `--count-blank-after-each-count` | off | Insert an all-black A frame after every displayed count. |
| `--preview-url` / `--preview-fps` | none / `1` | Opt-in rate-limited paired live-preview posting. |
| `-v`, `--verbose` | basic | Increase logging detail; repeat for source paths and full board snapshots. |

## Paired test modes

| `--test` | Description |
|----------|-------------|
| `checkerboard` | Static checkerboard on both DMDs, with independent `--test-a` / `--test-b` overrides. |
| `grid` | Thick paired alignment grid with route markers. |
| `bands` | Thick vertical/horizontal alignment bands. |
| `dot` | Static dot aperture on both routes. |
| `snake` | Dynamic grayscale snake on both routes. |
| `a-calibr-square-b-dot` | Interactive calibration square on A and a static dot on B. |
| `a-kernel-b-static` | 512-mask 3x3 kernel sequence on A and a selected static pattern on B. |
| `a-count-b-static` | Decimal count sequence on A and a selected static pattern on B. |
| `static-images` | Aspect-preserving static image on each DMD. |

Every paired mode requires `--exposure-us`. Static and recipe modes build explicit per-controller LUTs; dynamic modes
use the same configured timing while advancing the shared 3840x1080 source frame.

`--dark-time-us` is kept for LUT timing and budget accounting, but it does not work reliably as visible off-time in
DLPC900 Video Pattern Mode. For camera-visible off frames, use explicit blank frames or blank bitplanes instead. For
example, count-mode camera checks should use `--count-blank-after-each-count` rather than trying to make an off window
with `--dark-time-us`.

For `a-count-b-static`, omit `--count-slots-per-frame` or pass `--count-slots-per-frame auto` to choose the fastest slot
count that fits the LUT timing, evenly divides the count range, and stays within the 128-VSYNC count-sequence cap. In the
no-blank packed path, each RGB source frame carries multiple count masks in bitplanes such as `G0`, `G1`, `G2`, and `G3`.
The repeated DLPC900 LUT group uses Frame Change / WaitForTrigger only on LUT entry 0; later entries continue within the
same source VSYNC. Explicit integer overrides still work when you need a specific packed no-blank diagnostic.

Add `--count-blank-after-each-count` when each displayed count should be followed by an all-black A source frame:
`count 1`, `blank`, `count 2`, `blank`, and so on. This mode intentionally requires `--count-slots-per-frame 1`, uses one
LUT entry per 60 Hz source frame, and gives a 30 Hz number cadence because every other source frame is blank. B remains the
configured static pattern, and the expected trigger count doubles because the blank source frames also consume one LUT
trigger each. The older `--count-blank-between-frames` spelling is still accepted for existing scripts.
Paired modes are sequence-backed: the runtime builds one `PairedDisplaySequence` that owns the RGB source frames, the
LUT slots that consume their bitplanes, startup policy, preview metadata, and camera metadata. For count/blank mode, each
source frame uses bitplane 0 for exactly one semantic item: either `count:N` or `blank`, both using the requested exposure.
Live camera metadata includes `display_sequence` and `startup_leader` so notebooks can see the exact frame/LUT pairing
used during capture. Local fake-backed tests assert the same metadata without opening camera, X11, or USB hardware.
For count/static mode, DMD B now has an independent one-entry LUT: zero programmed dark time and no clear after the
last exposure, so the circle is held through VSYNC idle time. Its startup pair is A blank/B static, which illuminates
the circle before semantic count playback begins. DMD A retains the requested count/blank exposure and is the camera
timing source. Connect the event camera to A `TRIG_OUT_2`; use B `TRIG_OUT_2` only to measure paired-controller skew.
Camera global hold is preserved unless `--camera-global-hold on` or `--camera-global-hold off` is explicit, and supported
camera readbacks are stored under `camera_ready.camera_configuration`. Follow
[the count/static optical verification runbook](documentation/COUNT_STATIC_OPTICAL_VERIFICATION.md) for controlled runs.


For local camera-flow debugging without hardware, run `python -m pytest tests/test_camera_live_plumbing.py -q`. Those tests use fake camera/runtime objects while still exercising the live metadata, timing, trigger, and artifact plumbing paths.

Paired camera runs use one continuous OpenGL render coordinator through startup. It holds the mode's configured startup
pair before DLPC sequencer start, repeats that pair for `--paired-startup-leader-vsyncs` source VSYNCs after start, and
only then advances to semantic frames. Most modes use a blank pair; count/static uses A blank/B static. This avoids the
old startup-to-semantic render handoff while the DLPC900 sequencer is already running. The non-semantic leader trigger
count and frame role are recorded in `metadata.json` under `startup_leader`, then skipped before accumulation artifacts
are selected.

Paired presentation keeps one 3840x1080 GLFW drawable, one OpenGL context, and one
`swap_buffers()` call with `swap_interval(1)`. Two persistent 1920x1080 RGB textures are
updated with `glTexSubImage2D`: B is drawn into the left half and A into the right half.
Each quad reverses only its S texture coordinate, preserving the validated per-DMD horizontal
mirror without CPU `fliplr` copies or a 3840x1080 NumPy composition in the runtime path.

Rate-limited paired stutter warnings report input preparation, B upload, A upload, draw,
swap, total, target, and the slowest phase. Because OpenGL uploads may complete asynchronously,
a driver/GPU stall may appear in the swap phase. See the optical verification runbook above

Board-specific paired controller logs are tagged `[DMD A]` or `[DMD B]`, including nested USB,
setup, LUT-load, sequencer-start, and cleanup messages. Shared renderer and synchronization
messages remain untagged.



The A-side kernel recipe prepends `--kernel-leader-frames` all-black VSYNC frames to every cycle. With default fast
timing, `3` leader frames × `24` LUT entries means the first `72` `TRIG_OUT_2` pulses after kernel-cycle start are
leader pulses; kernel index 0 starts after that. Local timing coverage lives in `tests/test_kernel_runtime.py`; live
runtime logs print the active timing summary once hardware setup starts.

## Standalone tools

```bash
python -m dmdcontrol usb wake          # send DP-receiver wakeup only
python -m dmdcontrol usb discover      # list DLPC900 USB devices and mappings
```

## Camera sync-check notes

The normal camera entrypoints are:

```bash
./run_camera_sync_check.sh --exposure-us 16000 [other flags]
./run_dmd_pair_capture.sh --exposure-us 14000 [other flags]
```

Both camera launchers require an explicit positive --exposure-us and reject the command before opening the camera or configuring either DMD when it is missing. `dv_processing` camera API directly:

- Camera open defaults to `dv.io.camera.open()`.
- The open-time stale batch flush uses `--camera-flush-reads`, default `1`.
- No post-trigger grace reads are used unless `--camera-post-trigger-event-batches N` is passed. The default is `0`.

The extra camera flags are diagnostic switches, not normal-run requirements:

| Flag | Default | Use |
|------|---------|-----|
| `--camera-post-trigger-event-batches N` | `0` | Keep reading up to `N` event batches after the expected trigger count. This did not fix the current no-optical-response state. |
| `--bias-sensitivity` / `--efps` | `default` | Camera performance configuration through current DVXplorer contrast-threshold/readout APIs. Leave these at `default` unless deliberately testing camera settings. |

Current DVXplorer investigation state:

- Event counts alone are not enough evidence. A bad camera state can still stream background-like events while the spatial PNG looks like the no-stimulus noise image.
- Physical unplug/replug has restored stimulus-correlated optical response. Software open/close, stream rearm, and threshold changes have not reliably restored it.
- Under user `main` on `eodla`, `dv_processing` was observed as version `2.0.3`, with `dv.io.camera.open()` present.
- If Hannah's separate Linux user does not show this issue, first compare her Python/dv environment before changing sync-check logic.

Environment comparison command for each Linux user:

```bash
whoami
which python
python - <<'PY'
import dv_processing as dv
print(getattr(dv, "__version__", "unknown"))
print(getattr(dv, "__file__", None))
print("has camera.open", hasattr(dv.io, "camera") and hasattr(dv.io.camera, "open"))
PY
```

If a physical replug makes `camera_probe.py` images show the stimulus, treat the root cause as device/libcaer/dv-processing
state that needs a fuller hardware or driver-level reinitialization, not as a DMD timing or accumulation-window-only bug.

## Trigger output behavior

DLPC900 in Video Pattern Mode drives two GPIO trigger outputs. Their on-scope behavior surprises people, so:

- **TRIG_OUT_1 is advisory in our current hardware path.** TI documents it as the pattern-exposure gate, and without
  programmed dark time it may remain high for a whole pattern sequence. Empirically on the current setup it has also
  been observed staying low for the whole run. Do not use TRIG_OUT_1 for kernel indexing or acquisition truth; use
  `TRIG_OUT_2`. Been having problems with this trigger, not sure why.
- **TRIG_OUT_2 fires per bitplane** (or once per frame on bitplane 0 with `--trig2-frame-zero`). Default pulse width =
  20 µs. With 24 entries × 615 µs and dark=0, you get 24 pulses spaced 615 µs apart, then a ~1907 µs idle gap, then the
  next burst. **Scope auto-Hz reads ~1.63 kHz** because it windows over the dense burst region (1/615 µs ≈ 1626 Hz). *
  *Pulses per second over a 1.000 s counter gate = 1440** (24 × 60 frames). Both numbers are correct; they describe
  different things.
- For uniform 1440 Hz output (every pulse exactly 694 µs apart), you would need `dark=79` µs to push the per-entry
  period from 615 to 694, eliminating the VSYNC idle gap. The current `INTER_PATTERN_DARK_US = 0` in `config.py` is
  intentional — it maximizes integration time per bitplane.

### Hardware status bit interpretation

The DLPC900 hardware status register (read via cmd 0x1A0A) exposes status flags. Two are easy to misread:

- **Bit 6** behaves in our setup as a state-machine flag rather
  than a fault indicator. It is set after every `start_pattern_display(0)` (Pattern Stop) and persists until the next
  `start_pattern_display(2)` completes a clean handoff. It is also set at boot and persists across barrel power cycles.
  Treat as cosmetic when `sequencer_running`, `external_source_locked`, and `port1_syncs_valid` are all true and
  forced-swap (bit 3) and sequence-error (bit 7) are clear. `dlpc_lifecycle.apply_pattern_sequence` skips retry churn in
  that healthy state and retries only when bit 6 is paired with a real unhealthy signal.
- **Bit 7 ("Sequence Error Flag")** is the real runtime-error signal. If you see this set, investigate.

The runtime watchdog logs `hw=0x61` continuously when bit 0 (init_ok), bit 5 (reserved, commonly reads 1), and bit 6 (
cosmetic ABORT) are set. I think its a fine pattern

## Layout

```
dmdcontrol/         Package CLI, runtime, hardware, preview, and pattern modules
run_dmd_pair.sh     Paired Linux DMD launcher
run_dmd_pair_calibr_square.sh  Paired calibration launcher with terminal input
run_camera_sync_check.sh       Camera sync-check launcher
run_dmd_pair_capture.sh        Paired DMD + camera capture launcher
run_dmd_preview_server.sh      Preview server launcher, defaults to 0.0.0.0:8080
scripts/           Shared shell helpers, X11 layout helpers, and generic xinit client
compat/legacy/     Old Python entrypoint/import shims kept out of the repository root
sync_dmd.sh         rsync local -> lab box (bash)
sync_dmd.ps1        rsync local -> lab box (PowerShell)
context/            Notes (DP/X11 quirks, optical diffraction, sync)
documentation/      DLPC900 / DLPT028 / DLPU018J PDFs + extracted text
```

## Help

```bash
python -m dmdcontrol --help
python -m dmdcontrol pair run --help
python -m dmdcontrol pair calibrate --help
python -m dmdcontrol preview serve --help
python -m dmdcontrol usb discover --help
python -m dmdcontrol usb wake --help
python -m dmdcontrol config show --help
```
