# dmdcontrol CLI and Package Reorganization Design

## Purpose

Reorganize `dmdcontrol` from a flat collection of large runtime scripts into a maintainable Python package with a coherent command tree, while keeping the Linux DMD-box launch behavior available through shell wrappers. The refactor may change Python import paths and preferred command syntax, but all current essential capabilities must remain achievable.

## Current State

The project drives TI DLPC900 based DMD hardware in Video Pattern Mode. It includes single-DMD runtime, paired dual-DMD runtime, DisplayPort/X11 launch wrappers, USB discovery and wake helpers, preview rendering/server logic, calibration square control, kernel pattern playback, flood mode, and pytest coverage.

The current structure has too much behavior at the repository root:

- `main.py` mixes single-DMD CLI, timing summaries, frame-provider setup, video capture, hardware orchestration, and render-loop wiring.
- `main_pair.py` mixes paired CLI, paired config, recipe validation, frame-provider setup, live-preview metadata, paired pump control, and hardware orchestration.
- `dmd_preview_server.py` embeds HTML, CSS, JavaScript, HTTP routing, API payload shaping, and server startup in one file.
- `dlpc_lifecycle.py` contains important hardware sequencing and LUT behavior, but its public boundary is broad.
- The shell scripts are important, but their role is not clearly separated from Python runtime behavior.

Baseline test findings from the design scan:

- `python -m pytest` currently collects `server_backup/laser_test.py`, which imports undeclared `prettytable`. `server_backup` is ignored and should not be part of the active test suite.
- `python -m pytest tests -q` currently reports one stale preview UI test failure: the test expects `.preview-status-strip` and `.bottom-panel`, while the current HTML from commit `e34fda7` uses `.state-cache` and `.control-panel`.

## Architecture Boundary

Use a hard boundary between Linux session orchestration and Python runtime behavior.

Shell launchers own host and display-session concerns:

- DisplayPort wake sequencing.
- Hotplug wait timing.
- `sudo -S xinit ... < .env_pass` behavior.
- `xinitrc_dmd.sh` and `xinitrc_dmd_pair.sh` X11/NVIDIA modeline setup and verification.
- Calibration-square `/dev/tty` key reader and temporary control-file lifecycle.

Python package commands own DMD runtime concerns:

- CLI parsing and validation.
- DMD mapping config resolution.
- DLPC900 USB/HID protocol helpers.
- LUT timing and lifecycle orchestration.
- Single and paired frame-provider construction.
- Render-loop integration.
- Preview rendering, live preview posting, and preview HTTP serving.
- Dry-run timing validation that works without X11, OpenGL, USB, or real hardware.

This boundary avoids rewriting fragile X11, sudo, and terminal raw-mode behavior in Python during the cleanup pass. The shell scripts should become thinner and more explicit, but they remain supported production entry points for the Linux DMD box.

## Package Layout

Create a real package named `dmdcontrol`:

```text
dmdcontrol/
  __init__.py
  __main__.py
  cli/
    __init__.py
    main.py
    single.py
    pair.py
    preview.py
    usb.py
    flood.py
    config.py
  hardware/
    __init__.py
    dlpc900.py
    usb.py
    mapping.py
    wake.py
  runtime/
    __init__.py
    lifecycle.py
    single.py
    pair.py
    loop.py
    timing.py
  patterns/
    __init__.py
    engine.py
    paired.py
    modes.py
    visual.py
    calibration_square.py
    kernel.py
  preview/
    __init__.py
    render.py
    server.py
    html.py
    live.py
  support/
    __init__.py
    constants.py
    logging.py
```

Initial migration can keep compatibility shims at the root where useful. For example, `main.py`, `main_pair.py`, `dmd_preview_server.py`, `dmd_usb.py`, and `wake_dp.py` may temporarily delegate to package modules so existing tests and wrapper calls can migrate safely.

## Command Design

Add `python -m dmdcontrol` as the preferred Python command tree.

Single-DMD runtime:

```bash
python -m dmdcontrol single run --test snake --runtime-seconds 300
```

Paired runtime:

```bash
python -m dmdcontrol pair run \
  --mode a-kernel-b-static \
  --b-test dot \
  --b-dot-x 960 \
  --b-dot-y 540 \
  --b-dot-radius 40 \
  --kernel-px 201 \
  --runtime-seconds 999
```

Paired calibration square:

```bash
python -m dmdcontrol pair calibrate \
  --b-dot-x 960 \
  --b-dot-y 540 \
  --b-dot-radius 40 \
  --preview-url http://127.0.0.1:8080/api/live-frame \
  --preview-fps 1
```

Preview server:

```bash
python -m dmdcontrol preview serve --host 0.0.0.0 --port 8080
```

USB and utility commands:

```bash
python -m dmdcontrol usb discover
python -m dmdcontrol usb wake --dmd A
python -m dmdcontrol flood run --color white
python -m dmdcontrol config show --dmd A
```

Dry-run commands must remain available without X11, OpenGL, USB, or hardware:

```bash
python -m dmdcontrol pair run --dry-run-timing --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
python -m dmdcontrol pair calibrate --dry-run-timing --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

Flag cleanup:

- `pair run --mode` replaces paired `--test` in the preferred CLI.
- `--b-test` replaces `--test-b` in the preferred CLI.
- `pair calibrate` implies the old `--test a-calibr-square-b-dot` recipe.
- Existing script-level flags should either be translated by wrappers or accepted as hidden compatibility aliases during the transition.

## Compatibility Launchers

Keep these production shell launchers supported:

```bash
./run_dmd.sh
./run_dmd_pair.sh
./run_dmd_pair_calibr_square.sh
./run_calibr_square.sh
./run_flood_white_usb.sh
./discover_dmd_usb.sh
```

The launchers should continue to perform DP wake, hotplug wait, `xinit`, X11/NVIDIA setup, and calibration key-reader behavior. Internally, they should call `python -m dmdcontrol ...` through `xinitrc_dmd.sh` or `xinitrc_dmd_pair.sh` instead of calling large root-level Python scripts.

The following workflows are essential behavior contracts:

```bash
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
```

```bash
./run_dmd_pair_calibr_square.sh --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

Those exact old commands may be translated internally, and the README should document the preferred new form. The old production launch paths must still be achievable at the end of this cleanup pass.

## Preview Server Refactor

Split preview behavior into focused modules:

- `dmdcontrol.preview.render`: offline frame generation, bitplane extraction, PNG rendering, LUT preview metadata.
- `dmdcontrol.preview.live`: live frame store and live preview poster.
- `dmdcontrol.preview.html`: HTML/CSS/JavaScript asset string or template assembly.
- `dmdcontrol.preview.server`: request handler, API routes, config payloads, server creation.
- `dmdcontrol.cli.preview`: CLI entry for `preview serve`.

The existing stale test should be updated to match the current UI structure or, preferably, assert stable functional identifiers rather than outdated class names. The UI contract should protect controls and API behavior, not freeze incidental CSS class names from a prior design.

## Runtime Refactor

Single-DMD runtime should separate:

- Argument parser and CLI adapter.
- Timing summaries.
- Dry-run timing path.
- Frame-provider construction.
- Hardware initialization and lifecycle calls.
- Render-loop execution.

Paired runtime should separate:

- Pair config resolution.
- Paired recipe validation.
- Kernel/static recipe setup.
- Calibration-square/dot recipe setup.
- Live-preview metadata creation.
- Paired render pump control.
- Hardware sequence start and cleanup.

The old root scripts can remain as thin compatibility delegates while tests and shell wrappers migrate.

## Hardware And Lifecycle Refactor

Move hardware modules conservatively:

- `dlpc900_hid.py` to `dmdcontrol.hardware.dlpc900`.
- `dmd_usb.py` to `dmdcontrol.hardware.usb`.
- `dmd_config.py` to `dmdcontrol.hardware.mapping`.
- `wake_dp.py` behavior to `dmdcontrol.hardware.wake` plus `dmdcontrol usb wake`.
- `dlpc_lifecycle.py` to `dmdcontrol.runtime.lifecycle`.

Because real hardware verification will happen after the pass on the Linux DMD box, this stage should avoid behavior changes in USB packet formatting, LUT definition, sequencer start order, and status interpretation unless a test-covered bug is found.

## Tests

Local acceptance must include:

```bash
python -m pytest tests -q
python -m dmdcontrol pair run --dry-run-timing --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
python -m dmdcontrol pair calibrate --dry-run-timing --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
python -m dmdcontrol preview serve --help
```

Test cleanup requirements:

- Prevent ignored backup scripts from being collected by default pytest runs.
- Update preview server UI tests for the current functional UI contract.
- Add CLI tests for new command routing and dry-run validation.
- Keep current tests around paired frame composition, LUT timing, calibration square, USB mapping, and render preview behavior passing.

## README And Operator Docs

Update `README.md` to include:

- New package command tree.
- Production launcher responsibilities.
- Compatibility examples for old script workflows.
- Preferred new command equivalents.
- Dry-run validation examples.
- Preview server usage.
- Linux DMD-box hardware verification checklist.

The README must make it clear that shell wrappers are still the correct production entry points when `xinit`, DisplayPort wake, and calibration keyboard passthrough are required.

## Linux DMD-Box Verification Checklist

After local tests pass, the operator should verify these on the Linux hardware box:

```bash
python -m dmdcontrol preview serve --host 0.0.0.0 --port 8080
```

```bash
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
```

```bash
./run_dmd_pair_calibr_square.sh --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

```bash
./run_dmd.sh --test snake --runtime-seconds 300
```

```bash
./discover_dmd_usb.sh
```

Expected outcomes:

- X11 launches and verifies the configured display layout.
- DP wake still happens before `xinit`.
- Paired B-left/A-right layout is preserved.
- Kernel/static paired recipe renders A kernel frames and static B dot.
- Calibration square accepts W/A/S/D/Q/E/R/F and exits with ESC or X.
- Preview server receives live frames when `--preview-url` is used.
- DLPC900 status checks do not report forced swap or sequence error regressions.

## Non-Goals

- Do not port all shell orchestration to Python in this pass.
- Do not rewrite DLPC900 packet semantics without test evidence.
- Do not remove production shell launchers.
- Do not require hardware access for local completion.
- Do not change the scientific pattern semantics of kernel, calibration square, paired dot, or bitplane packing.

## Success Criteria

The cleanup is successful when:

- The codebase has a real `dmdcontrol` package with clear ownership boundaries.
- `python -m dmdcontrol ...` provides a coherent preferred CLI.
- Existing production shell launchers still reach the essential hardware workflows.
- Local tests pass under `python -m pytest tests -q`.
- The current baseline pytest collection issue is fixed.
- The current stale preview UI test is fixed.
- README documents new and compatibility commands clearly.
- The Linux DMD-box verification checklist is ready for final hardware validation.
