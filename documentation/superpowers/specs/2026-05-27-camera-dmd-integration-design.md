# Camera and DMD Integration Design

## Context

The next hardware workflow combines the paired DLPC900 DMD setup with one
iniVation DVXplorer event camera. The camera is connected to `TRIG_OUT_2` from
DMD A. The first target mode is a DMD/camera sync check: both DMDs display a
number sequence and the camera records triggered event data, then saves a full
run artifact directory.

This project is a hardware-control codebase first. Shell launchers remain the
real hardware entrypoints because they own DisplayPort wake, hotplug waits,
`xinit`, sudo/environment pass-through, X11/NVIDIA setup, and calibration
terminal wiring. The Python package owns structured intent, dry-runs, prepared-X
execution, camera capture, accumulation, and artifact writing.

Laser operation is explicitly out of scope. The implementation must not import
laser packages, open laser serial devices, set laser power, or enable/disable a
laser. Laser operation remains manual.

## Goals

- Add a single-process prepared-X coordinator for paired DMD plus DVXplorer
  capture.
- Add a sync-check mode that displays `1..5` on both DMDs, captures rising-edge
  triggered camera data, accumulates frames linearly, and writes a complete run
  directory.
- Make number size configurable in pixels.
- Preserve shell wrappers as hardware entrypoints.
- Keep camera imports lazy so non-camera CLI commands work without
  `dv_processing`.
- Add reusable capture and accumulation primitives for later `N kernels x M
  input images` capture.
- Move the requested `~3% of frame/exposure time` capture offset into DMD-side
  `TRIG_OUT_2` rising-edge timing and record the applied timing in metadata.

## Non-Goals

- No laser control.
- No direct bypass of shell launchers for real DMD hardware.
- No migration of X session setup or DisplayPort wake logic into Python.
- No full convolution/data-collection pipeline in the first implementation.
  The implementation will create the reusable capture/accumulation foundation
  and metadata shape needed for that next mode.
- No long-running camera loops in automated tests.

## User-Facing Commands

Add a camera CLI area:

```bash
python -m dmdcontrol camera discover
python -m dmdcontrol camera status
python -m dmdcontrol camera sync-check --dry-run
python -m dmdcontrol camera sync-check --number-size-px 420 --numbers 1,2,3,4,5
```

Add a shell hardware entrypoint for the sync check:

```bash
./run_camera_sync_check.sh --number-size-px 420
```

The shell launcher will follow the `run_dmd_pair.sh` pattern: parse DMD config
args, wake DMD A and B, wait for hotplug, start the paired X session, and run the
camera coordinator inside the prepared X session.

For later kernel/input work, the command shape should be compatible with
metadata needed by commands inspired by:

```bash
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 129 --kernel-exposure-us 3000 --runtime-seconds 999
```

The first implementation should not require this kernel command to run through
camera capture yet, but the run metadata and accumulation code must not be
sync-check specific.

## Architecture

### CLI Layer

Add `dmdcontrol.cli.camera`, routed from `dmdcontrol.cli.main`.

Responsibilities:

- Translate top-level `camera` subcommands.
- Keep `dv_processing` imports lazy.
- Provide `discover`, `status`, and `sync-check`.
- Provide dry-run/no-camera paths for development and CI.

### Camera Package

Add `dmdcontrol/camera/` with focused modules:

- `discovery.py`: defensive DVXplorer discovery and capability reporting.
- `capture.py`: live camera open/flush/record loop and `.aedat4` writer.
- `accumulation.py`: trigger filtering and linear event accumulation.
- `runs.py`: run directory creation and artifact writing.
- `sync_check.py`: high-level sync-check coordinator.

The package must use one live camera object at a time. It must not open a generic
capture and then another model-specific capture in the same process.

### Paired DMD Coordinator

Reuse the existing paired runtime pieces:

- `PairedPatternEngine`
- `_start_pair_pump`
- `prepare_dlpc900_for_video_pattern`
- `load_pattern_sequence`
- `start_loaded_pattern_sequences`

Add a coordinator path that prepares DMD A/B and camera concurrently:

1. Start paired OpenGL window and continuous pump of the idle/first frame.
2. Prepare DMD A and B for Video Pattern Mode.
3. Load matching LUTs without starting sequencers.
4. Open DVXplorer, verify event and trigger streams, configure rising-edge
   trigger detection only, flush stale batches, and open the run writer.
5. Wait for both DMDs and camera to report ready.
6. Release the run by starting both DLPC900 sequencers from the existing paired
   software barrier and starting/continuing camera collection.
7. Stop on expected trigger count, timeout, process exit, or error.
8. Stop DMD pattern display and close camera/writer in cleanup.

### Sync-Check Pattern

Add paired number sequence support for digits `1..5`.

Requirements:

- Both DMDs display the same digit sequence.
- Digit size is configurable in pixels.
- Default sequence is `1,2,3,4,5`.
- Exposure/dwell per number is configurable and saved in metadata.
- The pattern is binary RGB like the existing number mode.

This should extend existing number-generation helpers rather than creating a new
font/rendering system.

## DMD Trigger Timing

The requested camera capture timing offset should be applied on the DMD side.

Current paired/single preparation configures:

```text
TRIG_OUT_2 rising_delay_us=0, falling_delay_us=20
```

Add a configurable delay policy:

- Default `trigger_out_2_delay_fraction = 0.03`.
- Applied rising delay is approximately `3%` of the relevant exposure or frame
  timing.
- For LUT-driven bitplane timing, use `timing["exposure_us"]` as the default
  basis.
- For frame-level modes such as sync-check, record both the LUT exposure basis
  and the number dwell time in metadata so downstream processing can interpret
  trigger windows correctly.
- Preserve the minimum pulse width and DLPC900 non-inverted constraint
  (`rising_delay_us <= falling_delay_us`) by setting falling delay to at least
  `rising_delay_us + 20`.

Dry-run output and metadata must include:

- trigger output channel: `TRIG_OUT_2`
- trigger edge: rising only
- rising delay in microseconds
- falling delay in microseconds
- delay fraction
- delay basis

## Run Directory

Default root:

```text
runs/camera/YYYYMMDD-HHMMSS-<mode>/
```

Add `--output-root` to override the root.

Default artifacts:

- `raw.aedat4`: raw camera recording.
- `metadata.json`: structured run metadata.
- `command.txt`: exact command line and process environment summary.
- `run.log`: copied or directly written logger output for the run.
- `triggers.csv`: trigger index, timestamp, edge/polarity, and derived role.
- `accumulated.npy`: linear accumulated frame stack.
- `frame_0000.png`, etc.: per-trigger accumulated frame images.
- `contact_sheet.png`: overview image for quick inspection.
- `timing.json`: DMD timing, exposure, trigger configuration, expected counts.

Metadata must include:

- repository path and current working directory.
- Python executable/version and platform.
- package command and shell launcher command when available.
- DMD config path and resolved DMD A/B mappings.
- DMD mode, number sequence, number size, dwell/exposure values.
- LUT timing from DMD A and B.
- trigger output configuration and edge policy.
- camera descriptor and opened camera name.
- camera capabilities and resolution.
- expected trigger count and actual trigger count.
- accumulation settings.
- artifact file list.
- start/end timestamps and exit status.

The implementation can take extra time to save useful run data. Reliability and
post-run interpretability are more important than minimizing save latency.

## Accumulation

Linear accumulation should be implemented independently of live camera I/O so it
can be tested with synthetic data and later reused for kernel/input capture.

Default behavior:

- Use rising-edge triggers only.
- For each trigger, accumulate events in a window starting at the trigger
  timestamp. Because the DMD-side trigger is delayed by the requested `3%`, the
  camera-side default window does not apply an additional `3%` offset.
- Default window length is the relevant exposure/dwell time unless overridden.
- Count positive events by default.
- Support future options for signed polarity and ignore-polarity accumulation.
- Save array shape and orientation in metadata.

The implementation should avoid the inefficient old pattern of re-opening the
recording for every trigger. It should stream events once where practical, or use
indexed/numpy-based processing after recording.

## Kernel/Input Capture Foundation

The sync-check implementation must leave clear extension points for:

- `M` input images displayed on DMD A.
- `N` kernels or kernel masks displayed in sequence.
- Expected trigger count derived from `N * M` and polarity/sign splits when
  used.
- Recording run artifacts with the same directory schema.
- Capturing key timing values such as `--kernel-px`, `--kernel-exposure-us`,
  leader frames, blank end frames, and trigger maps.

The first implementation does not need to complete the full convolution command,
but should avoid names and metadata that assume the only possible mode is
sync-check.

## Error Handling

- If `dv_processing` is missing for camera commands, print a concise install
  hint and return non-zero.
- If no camera is discovered, fail before DMD release.
- If event or trigger stream is unavailable, fail before DMD release.
- If DMD readiness fails, close the camera and save failure metadata/logs when a
  run directory exists.
- If camera capture fails after release, stop DMD pattern display in cleanup and
  save partial artifacts when possible.
- If trigger count is lower or higher than expected, mark the run status as
  partial/mismatch in metadata instead of pretending success.

## Tests

Focused tests should cover:

- `python -m dmdcontrol camera ...` routing does not import `dv_processing`
  until a camera command needs it.
- Camera discovery/status handles descriptor objects defensively.
- Run directory planning creates stable filenames and metadata.
- Trigger filtering keeps rising edges only.
- Linear accumulation from synthetic events/triggers.
- PNG/contact-sheet generation from synthetic accumulated frames.
- TRIG_OUT_2 delay calculation, including the `3%` default and pulse width
  constraint.
- Sync-check dry-run path without OpenGL, USB, X11, or camera hardware.
- Existing paired DMD dry-run commands still exit 0.

Before claiming completion, run:

```bash
python -m pytest -q
git diff --check
python -m dmdcontrol pair run --dry-run-timing --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
python -m dmdcontrol pair calibrate --dry-run-timing --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
python -m dmdcontrol camera sync-check --dry-run
```

## Documentation

Update `README.md` and files under `documentation/` only. Do not create a
top-level `docs/` directory.

Documentation must explain:

- Shell wrapper is the real hardware entrypoint.
- Camera sync-check command.
- Run directory layout.
- DVXplorer dependency and discovery/status commands.
- Rising-edge-only trigger policy.
- DMD-side `TRIG_OUT_2` delay policy.
- Laser operation is manual and out of scope.

## Open Risks

- DVXplorer Python APIs may differ slightly between installed `dv-processing`
  versions, so camera access code should use defensive attribute checks.
- Paired DMD start remains a tight software barrier, not a hard hardware genlock.
- The exact mapping between displayed frame dwell and trigger count depends on
  LUT mode (`per_bitplane` vs `frame_zero`) and must be recorded in metadata.
- Real hardware validation must happen on the Linux DMD box with the camera
  connected.
