# dmdcontrol CLI and Package Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the flat DMD runtime scripts into a `dmdcontrol` Python package with a coherent `python -m dmdcontrol ...` CLI while preserving the Linux shell launchers for xinit, NVIDIA/X11 setup, DP wake, and calibration keyboard passthrough.

**Architecture:** Keep shell scripts responsible for host/session orchestration and make Python modules responsible for runtime behavior. Implement the new CLI first as a safe delegation layer, then move existing modules into package namespaces with root-level compatibility shims. Finish by updating shell wrappers and README recipes.

**Tech Stack:** Python 3.13+, argparse, pytest/unittest, Bash shell launchers, Xorg/xinit/xrandr/nvidia-settings on the Linux DMD box.

---

## File Structure

Create:

- `pytest.ini` - constrain default pytest discovery to `tests/`.
- `dmdcontrol/__init__.py` - package marker and version-neutral public package.
- `dmdcontrol/__main__.py` - `python -m dmdcontrol` entry point.
- `dmdcontrol/cli/__init__.py` - CLI package marker.
- `dmdcontrol/cli/main.py` - command tree and dispatcher.
- `dmdcontrol/cli/single.py` - `single run` adapter.
- `dmdcontrol/cli/pair.py` - `pair run` and `pair calibrate` adapters.
- `dmdcontrol/cli/preview.py` - `preview serve` adapter.
- `dmdcontrol/cli/usb.py` - `usb discover` and `usb wake` adapters.
- `dmdcontrol/cli/flood.py` - `flood run` adapter.
- `dmdcontrol/cli/config.py` - `config show` adapter.
- `dmdcontrol/support/`, `dmdcontrol/hardware/`, `dmdcontrol/runtime/`, `dmdcontrol/patterns/`, `dmdcontrol/preview/` - package-owned module homes.
- `tests/test_dmdcontrol_cli.py` - CLI routing and dry-run behavior tests.

Move package-owned implementation into:

- `config.py` -> `dmdcontrol/support/constants.py`
- `logger.py` -> `dmdcontrol/support/logging.py`
- `dmd_config.py` -> `dmdcontrol/hardware/mapping.py`
- `dmd_usb.py` -> `dmdcontrol/hardware/usb.py`
- `dlpc900_hid.py` -> `dmdcontrol/hardware/dlpc900.py`
- `wake_dp.py` -> `dmdcontrol/hardware/wake.py`
- `flood_white_usb.py` -> `dmdcontrol/hardware/flood.py`
- `dlpc_lifecycle.py` -> `dmdcontrol/runtime/lifecycle.py`
- `runtime_loop.py` -> `dmdcontrol/runtime/loop.py`
- `main.py` orchestration -> `dmdcontrol/runtime/single.py`
- `main_pair.py` orchestration -> `dmdcontrol/runtime/pair.py`
- `visual_patterns.py` -> `dmdcontrol/patterns/visual.py`
- `pattern_modes.py` -> `dmdcontrol/patterns/modes.py`
- `pattern_engine.py` -> `dmdcontrol/patterns/engine.py`
- `paired_pattern_engine.py` -> `dmdcontrol/patterns/paired.py`
- `kernel_runtime.py` -> `dmdcontrol/patterns/kernel.py`
- `calibration_square_runtime.py` -> `dmdcontrol/patterns/calibration_square.py`
- `dmd_preview_render.py` -> `dmdcontrol/preview/render.py`
- `dmd_preview_server.py` -> `dmdcontrol/preview/server.py` and `dmdcontrol/preview/html.py`

Keep root compatibility shims for the old module/script names until all shell wrappers and tests use package imports.

## Task 1: Restore Local Test Baseline

**Files:**
- Create: `pytest.ini`
- Modify: `tests/test_dmd_preview_server.py`

- [ ] **Step 1: Reproduce the two current baseline failures**

Run:

```bash
python -m pytest
python -m pytest tests -q
```

Expected before the fix:

```text
python -m pytest: ERROR collecting server_backup/laser_test.py because prettytable is missing
python -m pytest tests -q: one failure in test_root_uses_preview_card_and_bottom_controls_ui
```

- [ ] **Step 2: Add pytest discovery config**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
norecursedirs =
    .git
    .idea
    .ruff_cache
    __pycache__
    documentation
    server_backup
```

- [ ] **Step 3: Update stale preview UI assertions**

In `tests/test_dmd_preview_server.py`, update `test_root_uses_preview_card_and_bottom_controls_ui` so it checks the current UI contract:

```python
self.assertIn('id="sourceSwitch"', html)
self.assertIn('class="preview-card"', html)
self.assertIn('class="state-cache"', html)
self.assertIn('class="state-token"', html)
self.assertIn('id="liveStatus"', html)
self.assertIn('class="control-panel"', html)
self.assertIn('class="command-deck"', html)
self.assertIn('class="control-surface"', html)
self.assertIn('class="control-section source-section"', html)
self.assertIn('class="control-section refresh-section"', html)
self.assertIn('id="offlineControls"', html)
self.assertIn('id="liveControls"', html)
self.assertIn('id="lutSummary"', html)
self.assertIn('id="lutEntries"', html)
self.assertIn('id="planeButtons"', html)
self.assertIn('class="plane-grid"', html)
self.assertIn("els.offlineControls.hidden = live", html)
self.assertIn("els.liveControls.hidden = !live", html)
self.assertIn('params.set("view", "packed")', html)
self.assertNotIn("<h1", html)
self.assertNotIn("<h2", html)
self.assertNotIn("DisplayPort output", html)
self.assertNotIn("Packed Frame Preview", html)
self.assertNotIn('class="control-card"', html)
self.assertNotIn('class="preview-titlebar"', html)
self.assertNotIn('class="preview-badge-row"', html)
self.assertNotIn('class="preview-status-strip"', html)
self.assertNotIn('class="bottom-panel"', html)
self.assertNotIn('class="inspector-panel"', html)
self.assertNotIn("<aside>", html)
```

- [ ] **Step 4: Verify baseline is green**

Run:

```bash
python -m pytest
python -m pytest tests -q
```

Expected:

```text
79 passed
```

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/test_dmd_preview_server.py
git commit -m "test: restore pytest baseline"
```

## Task 2: Make Legacy Entrypoints Delegation-Friendly

**Files:**
- Modify: `main.py`
- Modify: `flood_white_usb.py`
- Test: `tests/test_dmdcontrol_cli.py`

- [ ] **Step 1: Write tests for argv-aware legacy entrypoints**

Create `tests/test_dmdcontrol_cli.py` with this initial content:

```python
import unittest
from unittest import mock


class LegacyEntrypointArgvTests(unittest.TestCase):
    def test_single_main_accepts_argv_for_dry_run_timing(self):
        import main

        with mock.patch.object(main, "_dry_run_timing", return_value=None) as dry_run:
            result = main.main(["--dry-run-timing", "--test", "checkerboard"])

        self.assertEqual(result, 0)
        dry_run.assert_called_once()

    def test_flood_main_accepts_argv_and_cancelled_confirmation(self):
        import flood_white_usb

        with mock.patch("builtins.input", return_value="n"):
            result = flood_white_usb.main(["--color", "white"])

        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_dmdcontrol_cli.py -q
```

Expected:

```text
FAIL because main.main and flood_white_usb.main do not both accept argv
```

- [ ] **Step 3: Update `main.py` to accept argv and return status codes**

Change the function signature and parser call:

```python
def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
```

In the dry-run path, return `0`:

```python
    if args.dry_run_timing:
        _dry_run_timing(args)
        return 0
```

At the end of the successful trigger/render path, return `0` after cleanup completes. Keep exception logging behavior conservative:

```python
    except Exception as exc:
        logger.exception(f"Runtime failed: {exc}")
        return 1
    finally:
        logger.info("[+] Cleaning up...")
        if dlpc is not None:
            dlpc.start_pattern_display(0)
            dlpc.set_display_mode(0x00)
            dlpc.apply_block_lock_workaround()
        if engine is not None:
            engine.cleanup()
```

Update the script guard:

```python
if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Update `flood_white_usb.py` to accept argv**

Change:

```python
def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
```

to:

```python
def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
```

- [ ] **Step 5: Verify tests**

Run:

```bash
python -m pytest tests/test_dmdcontrol_cli.py tests/test_main_post_arm_prime.py -q
```

Expected:

```text
passed
```

- [ ] **Step 6: Commit**

```bash
git add main.py flood_white_usb.py tests/test_dmdcontrol_cli.py
git commit -m "refactor: make legacy entrypoints argv-aware"
```

## Task 3: Add the `python -m dmdcontrol` CLI Delegation Layer

**Files:**
- Create: `dmdcontrol/__init__.py`
- Create: `dmdcontrol/__main__.py`
- Create: `dmdcontrol/cli/__init__.py`
- Create: `dmdcontrol/cli/main.py`
- Create: `dmdcontrol/cli/single.py`
- Create: `dmdcontrol/cli/pair.py`
- Create: `dmdcontrol/cli/preview.py`
- Create: `dmdcontrol/cli/usb.py`
- Create: `dmdcontrol/cli/flood.py`
- Create: `dmdcontrol/cli/config.py`
- Modify: `tests/test_dmdcontrol_cli.py`

- [ ] **Step 1: Add failing CLI tests**

Append these tests to `tests/test_dmdcontrol_cli.py`:

```python
class DmdcontrolCliRoutingTests(unittest.TestCase):
    def test_pair_run_translates_new_mode_and_b_test_flags(self):
        from dmdcontrol.cli import pair

        with mock.patch("main_pair.main", return_value=0) as legacy:
            result = pair.run([
                "--dry-run-timing",
                "--mode", "a-kernel-b-static",
                "--b-test", "dot",
                "--b-dot-x", "960",
            ])

        self.assertEqual(result, 0)
        legacy.assert_called_once_with([
            "--dry-run-timing",
            "--test", "a-kernel-b-static",
            "--test-b", "dot",
            "--b-dot-x", "960",
        ])

    def test_pair_calibrate_injects_recipe_and_runtime_zero(self):
        from dmdcontrol.cli import pair

        with mock.patch("main_pair.main", return_value=0) as legacy:
            result = pair.calibrate([
                "--dry-run-timing",
                "--b-dot-x", "960",
                "--preview-url", "http://127.0.0.1:8080/api/live-frame",
            ])

        self.assertEqual(result, 0)
        legacy.assert_called_once_with([
            "--test", "a-calibr-square-b-dot",
            "--runtime-seconds", "0",
            "--dry-run-timing",
            "--b-dot-x", "960",
            "--preview-url", "http://127.0.0.1:8080/api/live-frame",
        ])

    def test_top_level_cli_dispatches_preview_help_without_importing_hardware(self):
        from dmdcontrol.cli.main import main as cli_main

        with self.assertRaises(SystemExit) as raised:
            cli_main(["preview", "serve", "--help"])

        self.assertEqual(raised.exception.code, 0)
```

- [ ] **Step 2: Run the CLI tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_dmdcontrol_cli.py -q
```

Expected:

```text
FAIL because dmdcontrol package does not exist
```

- [ ] **Step 3: Create package entry files**

Create `dmdcontrol/__init__.py`:

```python
"""dmdcontrol runtime package."""
```

Create `dmdcontrol/__main__.py`:

```python
from dmdcontrol.cli.main import main


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `dmdcontrol/cli/__init__.py`:

```python
"""Command adapters for dmdcontrol."""
```

- [ ] **Step 4: Create CLI dispatcher**

Create `dmdcontrol/cli/main.py`:

```python
from __future__ import annotations

import argparse

from dmdcontrol.cli import config, flood, pair, preview, single, usb


def _add_passthrough_command(subparsers, name, help_text, handler):
    parser = subparsers.add_parser(name, help=help_text)
    parser.set_defaults(handler=handler)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dmdcontrol")
    areas = parser.add_subparsers(dest="area", required=True)

    single_parser = areas.add_parser("single", help="single-DMD runtime commands")
    single_commands = single_parser.add_subparsers(dest="command", required=True)
    _add_passthrough_command(single_commands, "run", "run the single-DMD runtime", single.run)

    pair_parser = areas.add_parser("pair", help="paired dual-DMD runtime commands")
    pair_commands = pair_parser.add_subparsers(dest="command", required=True)
    _add_passthrough_command(pair_commands, "run", "run a paired recipe", pair.run)
    _add_passthrough_command(pair_commands, "calibrate", "run paired calibration square with static B dot", pair.calibrate)

    preview_parser = areas.add_parser("preview", help="preview server commands")
    preview_commands = preview_parser.add_subparsers(dest="command", required=True)
    _add_passthrough_command(preview_commands, "serve", "serve the preview UI", preview.serve)

    usb_parser = areas.add_parser("usb", help="USB discovery and wake commands")
    usb_commands = usb_parser.add_subparsers(dest="command", required=True)
    _add_passthrough_command(usb_commands, "discover", "discover DLPC900 USB mappings", usb.discover)
    _add_passthrough_command(usb_commands, "wake", "wake a DLPC900 DisplayPort receiver", usb.wake)

    flood_parser = areas.add_parser("flood", help="solid flood commands")
    flood_commands = flood_parser.add_subparsers(dest="command", required=True)
    _add_passthrough_command(flood_commands, "run", "configure a USB solid flood", flood.run)

    config_parser = areas.add_parser("config", help="mapping config commands")
    config_commands = config_parser.add_subparsers(dest="command", required=True)
    _add_passthrough_command(config_commands, "show", "show configured DMD mapping", config.show)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args, passthrough = parser.parse_known_args(argv)
    return args.handler(passthrough)
```

- [ ] **Step 5: Create CLI adapter modules**

Create `dmdcontrol/cli/single.py`:

```python
from __future__ import annotations


def run(argv=None) -> int:
    import main as legacy_single

    return int(legacy_single.main(list(argv or [])) or 0)
```

Create `dmdcontrol/cli/pair.py`:

```python
from __future__ import annotations


def _translate_pair_run_args(argv):
    translated = []
    args = list(argv or [])
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--mode":
            translated.append("--test")
            if i + 1 < len(args):
                translated.append(args[i + 1])
                i += 2
                continue
        elif arg.startswith("--mode="):
            translated.append("--test=" + arg.split("=", 1)[1])
            i += 1
            continue
        elif arg == "--b-test":
            translated.append("--test-b")
            if i + 1 < len(args):
                translated.append(args[i + 1])
                i += 2
                continue
        elif arg.startswith("--b-test="):
            translated.append("--test-b=" + arg.split("=", 1)[1])
            i += 1
            continue
        translated.append(arg)
        i += 1
    return translated


def run(argv=None) -> int:
    import main_pair

    return int(main_pair.main(_translate_pair_run_args(argv)) or 0)


def calibrate(argv=None) -> int:
    import main_pair

    args = list(argv or [])
    translated = ["--test", "a-calibr-square-b-dot"]
    if "--runtime-seconds" not in args and not any(arg.startswith("--runtime-seconds=") for arg in args):
        translated.extend(["--runtime-seconds", "0"])
    translated.extend(args)
    return int(main_pair.main(translated) or 0)
```

Create `dmdcontrol/cli/preview.py`:

```python
from __future__ import annotations


def serve(argv=None) -> int:
    import dmd_preview_server

    return int(dmd_preview_server.main(list(argv or [])) or 0)
```

Create `dmdcontrol/cli/usb.py`:

```python
from __future__ import annotations


def discover(argv=None) -> int:
    import dmd_usb

    return int(dmd_usb.main(list(argv or [])) or 0)


def wake(argv=None) -> int:
    import wake_dp

    return int(wake_dp.main(list(argv or [])) or 0)
```

Create `dmdcontrol/cli/flood.py`:

```python
from __future__ import annotations


def run(argv=None) -> int:
    import flood_white_usb

    return int(flood_white_usb.main(list(argv or [])) or 0)
```

Create `dmdcontrol/cli/config.py`:

```python
from __future__ import annotations

from dataclasses import asdict
import json


def show(argv=None) -> int:
    import argparse
    from dmd_config import resolve_dmd_mapping

    parser = argparse.ArgumentParser(prog="dmdcontrol config show")
    parser.add_argument("--dmd", required=True)
    parser.add_argument("--config", default=None)
    parser.add_argument("--field", default=None)
    args = parser.parse_args(argv)

    mapping = resolve_dmd_mapping(args.dmd, args.config)
    if args.field:
        value = getattr(mapping, args.field)
        print("" if value is None else value)
    else:
        print(json.dumps(asdict(mapping), indent=2, sort_keys=True))
    return 0
```

- [ ] **Step 6: Verify CLI adapter tests**

Run:

```bash
python -m pytest tests/test_dmdcontrol_cli.py -q
python -m dmdcontrol preview serve --help
```

Expected:

```text
tests pass
preview help exits with status 0 and prints serve options
```

- [ ] **Step 7: Commit**

```bash
git add dmdcontrol tests/test_dmdcontrol_cli.py
git commit -m "feat: add dmdcontrol command tree"
```

## Task 4: Verify Essential Dry-Run Commands Through the New CLI

**Files:**
- Modify: `tests/test_dmdcontrol_cli.py`

- [ ] **Step 1: Add subprocess smoke tests for essential dry-run commands**

Append:

```python
import subprocess
import sys


class DmdcontrolCliSmokeTests(unittest.TestCase):
    def test_pair_kernel_static_dry_run_command(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "dmdcontrol",
                "pair",
                "run",
                "--dry-run-timing",
                "--mode",
                "a-kernel-b-static",
                "--b-test",
                "dot",
                "--b-dot-x",
                "960",
                "--b-dot-y",
                "540",
                "--b-dot-radius",
                "40",
                "--kernel-px",
                "201",
                "--runtime-seconds",
                "999",
            ],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_pair_calibrate_dry_run_command(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "dmdcontrol",
                "pair",
                "calibrate",
                "--dry-run-timing",
                "--b-dot-x",
                "960",
                "--b-dot-y",
                "540",
                "--b-dot-radius",
                "40",
                "--preview-url",
                "http://127.0.0.1:8080/api/live-frame",
                "--preview-fps",
                "1",
            ],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
```

- [ ] **Step 2: Run smoke tests**

Run:

```bash
python -m pytest tests/test_dmdcontrol_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_dmdcontrol_cli.py
git commit -m "test: cover essential dmdcontrol dry-run commands"
```

## Task 5: Move Support, Hardware, Pattern, Runtime, and Preview Render Modules

**Files:**
- Create package module files under `dmdcontrol/support`, `dmdcontrol/hardware`, `dmdcontrol/runtime`, `dmdcontrol/patterns`, `dmdcontrol/preview`
- Modify root files into compatibility shims
- Modify imports in package-owned modules
- Test: existing tests

- [ ] **Step 1: Create package subdirectories and `__init__.py` files**

Create empty package markers:

```text
dmdcontrol/support/__init__.py
dmdcontrol/hardware/__init__.py
dmdcontrol/runtime/__init__.py
dmdcontrol/patterns/__init__.py
dmdcontrol/preview/__init__.py
```

Each file should contain:

```python
"""Package namespace."""
```

- [ ] **Step 2: Move implementation files into package paths**

Use file moves that preserve content:

```bash
git mv config.py dmdcontrol/support/constants.py
git mv logger.py dmdcontrol/support/logging.py
git mv dmd_config.py dmdcontrol/hardware/mapping.py
git mv dmd_usb.py dmdcontrol/hardware/usb.py
git mv dlpc900_hid.py dmdcontrol/hardware/dlpc900.py
git mv wake_dp.py dmdcontrol/hardware/wake.py
git mv flood_white_usb.py dmdcontrol/hardware/flood.py
git mv dlpc_lifecycle.py dmdcontrol/runtime/lifecycle.py
git mv runtime_loop.py dmdcontrol/runtime/loop.py
git mv visual_patterns.py dmdcontrol/patterns/visual.py
git mv pattern_modes.py dmdcontrol/patterns/modes.py
git mv pattern_engine.py dmdcontrol/patterns/engine.py
git mv paired_pattern_engine.py dmdcontrol/patterns/paired.py
git mv kernel_runtime.py dmdcontrol/patterns/kernel.py
git mv calibration_square_runtime.py dmdcontrol/patterns/calibration_square.py
git mv dmd_preview_render.py dmdcontrol/preview/render.py
```

- [ ] **Step 3: Add root compatibility shims**

Recreate each moved root module with a direct re-export. Use this pattern, changing the import target for each file:

```python
"""Compatibility shim for the package module."""

from dmdcontrol.support.constants import *  # noqa: F401,F403
```

Required shim mappings:

```text
config.py -> dmdcontrol.support.constants
logger.py -> dmdcontrol.support.logging
dmd_config.py -> dmdcontrol.hardware.mapping
dmd_usb.py -> dmdcontrol.hardware.usb
dlpc900_hid.py -> dmdcontrol.hardware.dlpc900
wake_dp.py -> dmdcontrol.hardware.wake
flood_white_usb.py -> dmdcontrol.hardware.flood
dlpc_lifecycle.py -> dmdcontrol.runtime.lifecycle
runtime_loop.py -> dmdcontrol.runtime.loop
visual_patterns.py -> dmdcontrol.patterns.visual
pattern_modes.py -> dmdcontrol.patterns.modes
pattern_engine.py -> dmdcontrol.patterns.engine
paired_pattern_engine.py -> dmdcontrol.patterns.paired
kernel_runtime.py -> dmdcontrol.patterns.kernel
calibration_square_runtime.py -> dmdcontrol.patterns.calibration_square
dmd_preview_render.py -> dmdcontrol.preview.render
```

For root scripts that must still execute directly, include the script guard:

```python
"""Compatibility shim for the package module."""

from dmdcontrol.hardware.usb import *  # noqa: F401,F403
from dmdcontrol.hardware.usb import main


if __name__ == "__main__":
    raise SystemExit(main())
```

Use that script-guard pattern for `dmd_config.py`, `dmd_usb.py`, `wake_dp.py`, and `flood_white_usb.py`.

- [ ] **Step 4: Update package imports away from root shims**

Within files under `dmdcontrol/`, replace root imports with package imports:

```python
from config import BITPLANES
```

becomes:

```python
from dmdcontrol.support.constants import BITPLANES
```

```python
from logger import logger, setup_logger
```

becomes:

```python
from dmdcontrol.support.logging import logger, setup_logger
```

```python
from pattern_modes import PATTERN_NAMES
```

becomes:

```python
from dmdcontrol.patterns.modes import PATTERN_NAMES
```

Apply equivalent replacements for moved modules.

- [ ] **Step 5: Update CLI adapters to import package modules**

Change:

```python
import dmd_usb
import wake_dp
import flood_white_usb
from dmd_config import resolve_dmd_mapping
```

to:

```python
from dmdcontrol.hardware import usb as dmd_usb
from dmdcontrol.hardware import wake as wake_dp
from dmdcontrol.hardware import flood as flood_white_usb
from dmdcontrol.hardware.mapping import resolve_dmd_mapping
```

- [ ] **Step 6: Verify full local suite**

Run:

```bash
python -m pytest tests -q
python -m dmdcontrol pair run --dry-run-timing --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
python -m dmdcontrol pair calibrate --dry-run-timing --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

Expected:

```text
tests pass
both dry-run commands exit 0
```

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "refactor: move core modules into dmdcontrol package"
```

## Task 6: Move Single and Pair Runtimes Behind Package Entrypoints

**Files:**
- Move: `main.py` -> `dmdcontrol/runtime/single.py`
- Move: `main_pair.py` -> `dmdcontrol/runtime/pair.py`
- Create/modify root shims: `main.py`, `main_pair.py`
- Modify: `dmdcontrol/cli/single.py`
- Modify: `dmdcontrol/cli/pair.py`
- Test: `tests/test_dmdcontrol_cli.py`, current runtime tests

- [ ] **Step 1: Move runtime scripts**

```bash
git mv main.py dmdcontrol/runtime/single.py
git mv main_pair.py dmdcontrol/runtime/pair.py
```

- [ ] **Step 2: Create root compatibility shim for `main.py`**

```python
"""Compatibility entrypoint for the single-DMD runtime."""

from dmdcontrol.runtime.single import *  # noqa: F401,F403
from dmdcontrol.runtime.single import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Create root compatibility shim for `main_pair.py`**

```python
"""Compatibility entrypoint for the paired dual-DMD runtime."""

from dmdcontrol.runtime.pair import *  # noqa: F401,F403
from dmdcontrol.runtime.pair import main
from dmdcontrol.support.logging import logger


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception(f"[ERROR] {exc}")
        raise SystemExit(1)
```

- [ ] **Step 4: Update CLI runtime adapters**

In `dmdcontrol/cli/single.py`:

```python
from __future__ import annotations


def run(argv=None) -> int:
    from dmdcontrol.runtime import single

    return int(single.main(list(argv or [])) or 0)
```

In `dmdcontrol/cli/pair.py`, replace `import main_pair` with:

```python
from dmdcontrol.runtime import pair as pair_runtime
```

Then call:

```python
return int(pair_runtime.main(_translate_pair_run_args(argv)) or 0)
```

and:

```python
return int(pair_runtime.main(translated) or 0)
```

- [ ] **Step 5: Update package imports inside moved runtime files**

Inside `dmdcontrol/runtime/single.py` and `dmdcontrol/runtime/pair.py`, use package imports:

```python
from dmdcontrol.support.constants import BITPLANES, DEFAULT_SEQUENCE_UTILIZATION, SAFE_MARGIN_US
from dmdcontrol.support.logging import logger, setup_logger
from dmdcontrol.runtime.lifecycle import ...
from dmdcontrol.runtime.loop import ...
from dmdcontrol.patterns.modes import ...
from dmdcontrol.patterns.engine import PatternEngine
from dmdcontrol.patterns.paired import ...
from dmdcontrol.patterns.kernel import ...
from dmdcontrol.patterns.calibration_square import ...
from dmdcontrol.preview.render import LivePreviewPoster, build_lut_preview_metadata
from dmdcontrol.hardware.mapping import resolve_dmd_mapping
```

- [ ] **Step 6: Verify runtime import compatibility**

Run:

```bash
python -m pytest tests/test_main_post_arm_prime.py tests/test_main_pair_config.py tests/test_dmdcontrol_cli.py -q
python main.py --dry-run-timing --test checkerboard
python main_pair.py --dry-run-timing --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201
python -m dmdcontrol pair run --dry-run-timing --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
```

Expected:

```text
tests pass
legacy direct script dry-runs exit 0
new CLI dry-run exits 0
```

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "refactor: move runtime entrypoints into package"
```

## Task 7: Split Preview Server HTML From HTTP Routing

**Files:**
- Move/split: `dmd_preview_server.py` -> `dmdcontrol/preview/server.py`, `dmdcontrol/preview/html.py`
- Modify: root `dmd_preview_server.py` compatibility shim
- Modify: `dmdcontrol/cli/preview.py`
- Test: `tests/test_dmd_preview_server.py`, `tests/test_dmdcontrol_cli.py`

- [ ] **Step 1: Move server implementation**

```bash
git mv dmd_preview_server.py dmdcontrol/preview/server.py
```

- [ ] **Step 2: Extract `INDEX_HTML` to `dmdcontrol/preview/html.py`**

Create `dmdcontrol/preview/html.py`:

```python
"""Browser UI asset for the DMD preview server."""

INDEX_HTML = """<!doctype html>
...
</html>
"""
```

Move the current full `INDEX_HTML` string from `dmdcontrol/preview/server.py` into that file without changing its body.

In `dmdcontrol/preview/server.py`, replace the embedded constant with:

```python
from dmdcontrol.preview.html import INDEX_HTML
```

Also update preview imports:

```python
from dmdcontrol.preview.render import (
    BITPLANE_LABELS,
    LiveFrameStore,
    render_png_bytes,
    render_preview_png,
    render_view_image,
)
from dmdcontrol.patterns.paired import PAIR_TESTS, STATIC_PAIR_TESTS
from dmdcontrol.patterns.modes import PATTERN_NAMES
```

- [ ] **Step 3: Add root server compatibility shim**

Create `dmd_preview_server.py`:

```python
"""Compatibility entrypoint for the DMD preview server."""

from dmdcontrol.preview.server import *  # noqa: F401,F403
from dmdcontrol.preview.server import main


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Update preview CLI adapter**

In `dmdcontrol/cli/preview.py`:

```python
from __future__ import annotations


def serve(argv=None) -> int:
    from dmdcontrol.preview import server

    return int(server.main(list(argv or [])) or 0)
```

- [ ] **Step 5: Verify preview tests and CLI help**

Run:

```bash
python -m pytest tests/test_dmd_preview_server.py tests/test_dmd_preview_render.py tests/test_dmdcontrol_cli.py -q
python -m dmdcontrol preview serve --help
python dmd_preview_server.py --help
```

Expected:

```text
tests pass
both help commands exit 0
```

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "refactor: split preview server package modules"
```

## Task 8: Update Shell Wrappers To Launch the Package CLI

**Files:**
- Modify: `dmd_shell_common.sh`
- Modify: `run_dmd.sh`
- Modify: `run_dmd_pair.sh`
- Modify: `run_dmd_pair_calibr_square.sh`
- Modify: `run_calibr_square.sh`
- Modify: `run_flood_white_usb.sh`
- Modify: `discover_dmd_usb.sh`
- Modify: `xinitrc_dmd.sh`
- Modify: `xinitrc_dmd_pair.sh`
- Modify: `tests/test_pair_wrappers.py`

- [ ] **Step 1: Update wrapper tests first**

In `tests/test_pair_wrappers.py`, update expectations from root Python script calls to package module calls:

```python
self.assertIn('dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair run "$@"', script)
```

For `xinitrc_dmd.sh`, assert:

```python
self.assertIn('dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol single run --monitor "$MONITOR_INDEX" "$@"', script)
```

For `xinitrc_dmd_pair.sh`, assert:

```python
self.assertIn('dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair run "$@"', script)
```

Keep the assertions that shell scripts source `dmd_shell_common.sh` and that xinit scripts source `dmd_x11_common.sh`.

- [ ] **Step 2: Run wrapper tests and confirm they fail**

Run:

```bash
python -m pytest tests/test_pair_wrappers.py -q
```

Expected:

```text
FAIL because scripts still call main.py/main_pair.py directly
```

- [ ] **Step 3: Add package module execution helper**

In `dmd_shell_common.sh`, keep `dmd_exec_python_entrypoint` for compatibility and add:

```bash
dmd_exec_python_module() {
    local script_dir="$1"
    local module="$2"
    shift 2
    exec env PYTHONPATH="$script_dir:/home/main/.local/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}" \
        /usr/bin/python3 -m "$module" "$@"
}
```

- [ ] **Step 4: Update xinit scripts**

In `xinitrc_dmd.sh`, replace:

```bash
echo "=== Launching main.py ==="
dmd_exec_python_entrypoint "$SCRIPT_DIR" main.py --monitor "$MONITOR_INDEX" "$@"
```

with:

```bash
echo "=== Launching dmdcontrol single run ==="
dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol single run --monitor "$MONITOR_INDEX" "$@"
```

In `xinitrc_dmd_pair.sh`, replace:

```bash
echo "=== Launching main_pair.py ==="
dmd_exec_python_entrypoint "$SCRIPT_DIR" main_pair.py "$@"
```

with:

```bash
echo "=== Launching dmdcontrol pair run ==="
dmd_exec_python_module "$SCRIPT_DIR" dmdcontrol pair run "$@"
```

- [ ] **Step 5: Update dry-run shell paths**

In `run_dmd_pair.sh`, replace:

```bash
exec /usr/bin/python3 "$SCRIPT_DIR/main_pair.py" "$@"
```

with:

```bash
exec env PYTHONPATH="$SCRIPT_DIR:/home/main/.local/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}" \
    /usr/bin/python3 -m dmdcontrol pair run "$@"
```

In `run_dmd_pair_calibr_square.sh`, replace:

```bash
exec /usr/bin/python3 "$SCRIPT_DIR/main_pair.py" --test a-calibr-square-b-dot "$@"
```

with:

```bash
exec env PYTHONPATH="$SCRIPT_DIR:/home/main/.local/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}" \
    /usr/bin/python3 -m dmdcontrol pair calibrate "$@"
```

Do not change the `/dev/tty` control-reader flow.

- [ ] **Step 6: Update utility shell wrappers**

Use package commands in the utility wrappers:

```bash
python -m dmdcontrol usb discover
python -m dmdcontrol usb wake
python -m dmdcontrol flood run
```

Keep each wrapper's existing shell safety checks and user-facing messages.

- [ ] **Step 7: Verify shell wrapper tests**

Run:

```bash
python -m pytest tests/test_pair_wrappers.py tests/test_dmdcontrol_cli.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

```bash
git add dmd_shell_common.sh run_dmd.sh run_dmd_pair.sh run_dmd_pair_calibr_square.sh run_calibr_square.sh run_flood_white_usb.sh discover_dmd_usb.sh xinitrc_dmd.sh xinitrc_dmd_pair.sh tests/test_pair_wrappers.py
git commit -m "refactor: route shell launchers through package CLI"
```

## Task 9: Update README With New CLI And Hardware Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README sections**

Add or replace the command sections so they contain:

```markdown
## Command Model

`dmdcontrol` now has two layers:

- Shell launchers own Linux DMD-box session setup: DisplayPort wake, hotplug wait, sudo/xinit, X11/NVIDIA modelines, and calibration keyboard passthrough.
- `python -m dmdcontrol ...` owns Python runtime behavior: CLI validation, mapping resolution, frame providers, LUT timing, preview rendering, USB discovery, and dry-run timing.

Use shell launchers for production hardware runs that need xinit:

```bash
./run_dmd.sh --test snake --runtime-seconds 300
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
./run_dmd_pair_calibr_square.sh --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
```

Use the Python CLI for dry-runs, preview, and direct runtime calls inside an already prepared display session:

```bash
python -m dmdcontrol single run --test snake --runtime-seconds 300
python -m dmdcontrol pair run --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
python -m dmdcontrol pair calibrate --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
python -m dmdcontrol preview serve --host 0.0.0.0 --port 8080
python -m dmdcontrol usb discover
python -m dmdcontrol usb wake --dmd A
python -m dmdcontrol flood run --color white
python -m dmdcontrol config show --dmd A
```
```

- [ ] **Step 2: Add hardware verification checklist**

Add:

```markdown
## Linux DMD-Box Verification After Refactor

Run these after local tests pass:

```bash
python -m dmdcontrol preview serve --host 0.0.0.0 --port 8080
./run_dmd_pair.sh --test a-kernel-b-static --test-b dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
./run_dmd_pair_calibr_square.sh --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
./run_dmd.sh --test snake --runtime-seconds 300
./discover_dmd_usb.sh
```

Expected:

- X11 launches and verifies the configured display layout.
- DP wake runs before `xinit`.
- Paired layout remains B on the left and A on the right.
- Kernel/static paired recipe renders A kernel frames and B static dot.
- Calibration square accepts W/A/S/D/Q/E/R/F and exits with ESC or X.
- Preview server receives live frames when `--preview-url` is used.
- DLPC900 runtime checks do not show forced-swap or sequence-error regressions.
```

- [ ] **Step 3: Verify README references**

Run:

```bash
rg -n "python -m dmdcontrol|run_dmd_pair_calibr_square|a-kernel-b-static|Linux DMD-Box Verification" README.md
```

Expected:

```text
all key command references are present
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document dmdcontrol package CLI"
```

## Task 10: Final Verification And Cleanup

**Files:**
- Inspect all changed files
- No new source files unless verification reveals a specific issue

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Run command acceptance checks**

```bash
python -m dmdcontrol pair run --dry-run-timing --mode a-kernel-b-static --b-test dot --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --kernel-px 201 --runtime-seconds 999
python -m dmdcontrol pair calibrate --dry-run-timing --b-dot-x 960 --b-dot-y 540 --b-dot-radius 40 --preview-url http://127.0.0.1:8080/api/live-frame --preview-fps 1
python -m dmdcontrol preview serve --help
python -m dmdcontrol usb discover --help
python -m dmdcontrol flood run --help
python -m dmdcontrol config show --help
```

Expected:

```text
all commands exit 0
```

- [ ] **Step 3: Scan for stale root imports inside package code**

Run:

```bash
rg -n "from (config|logger|dmd_config|dmd_usb|dlpc900_hid|dlpc_lifecycle|runtime_loop|pattern_modes|pattern_engine|paired_pattern_engine|kernel_runtime|calibration_square_runtime|dmd_preview_render)|import (config|logger|dmd_config|dmd_usb|dlpc900_hid|dlpc_lifecycle|runtime_loop|pattern_modes|pattern_engine|paired_pattern_engine|kernel_runtime|calibration_square_runtime|dmd_preview_render)" dmdcontrol
```

Expected:

```text
no matches, except intentional compatibility comments if any
```

- [ ] **Step 4: Inspect git diff**

```bash
git diff --stat
git diff --check
git status --short
```

Expected:

```text
diff contains only planned reorganization, tests, wrappers, and README changes
git diff --check reports no whitespace errors
```

- [ ] **Step 5: Final commit**

If any final cleanup changes were required:

```bash
git add .
git commit -m "chore: finalize dmdcontrol reorganization"
```

If no final cleanup changes were required, do not create an empty commit.

## Plan Self-Review

Spec coverage:

- Package command tree is covered by Tasks 3 and 4.
- Shell/Python boundary is preserved by Task 8.
- Preview split is covered by Task 7.
- Runtime and module migration is covered by Tasks 5 and 6.
- Baseline bug fixes are covered by Task 1.
- README and Linux DMD-box verification checklist are covered by Task 9.
- Local acceptance commands are covered by Task 10.

Placeholder scan:

- The plan intentionally contains no unresolved marker words or unspecified implementation areas.

Type and name consistency:

- Preferred paired CLI uses `--mode` and `--b-test`.
- Legacy paired runtime still receives `--test` and `--test-b`.
- `pair calibrate` injects `--test a-calibr-square-b-dot` and `--runtime-seconds 0`.
- Shell wrappers continue to own `xinit`, hotplug waits, `.env_pass`, and calibration `/dev/tty` control reading.
