from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from functools import partial
from pathlib import Path

from rich.logging import RichHandler

from dmdcontrol.utils import CONFIG, WORKSPACE

log = logging.getLogger("main")

RUN = CONFIG.get("Run", {})
DMD_CFG = CONFIG.get("DMD", {})
DISPLAY_ID = ":0"


def create_run_directory() -> Path:
    root = WORKSPACE / str(RUN.get("output_root", "runs"))
    run_dir = root / f"{datetime.now():%Y%m%d-%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def git_hash() -> str:
    """Short commit hash of the checkout, with -dirty if there are uncommitted changes."""
    try:
        return subprocess.run(
            ["git", "-C", str(WORKSPACE), "describe", "--always", "--dirty"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def setup_logging(run_dir: Path) -> None:
    level = getattr(logging, str(CONFIG.get("log_level", "INFO")).upper(), logging.INFO)
    console_handler = RichHandler(
        show_path=False, rich_tracebacks=True, markup=False,
        omit_repeated_times=False, log_time_format="%H:%M:%S",
    )
    console_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [console_handler, file_handler]
    logging.getLogger("OpenGL").setLevel(logging.INFO)  # third-party logs


def wake_dmds(dlpc_a, dlpc_b) -> None:
    for name, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
        log.info("Waking DisplayPort receiver on DMD %s", name)
        dlpc.wake_displayport_receiver()
        time.sleep(1)
        dlpc.set_input_source(0, 1)
        dlpc.set_display_mode(0)
        dlpc.apply_block_lock_workaround()


def setup_displays() -> None:
    script = WORKSPACE / "scripts" / "setup_displays.sh"
    log.info("Running display setup: %s", script)
    subprocess.run(["bash", str(script)], check=True)
    os.environ.setdefault("DISPLAY", DISPLAY_ID)


def validate_display() -> None:
    out_a = DMD_CFG["A"]["xrandr_output"]
    out_b = DMD_CFG["B"]["xrandr_output"]
    query = subprocess.run(
        ["xrandr", "--display", os.environ.get("DISPLAY", DISPLAY_ID), "--query"],
        capture_output=True, text=True, check=True,
    ).stdout
    problems = []
    if "current 3840 x 1080" not in query:
        problems.append("screen is not 3840x1080")
    if f"{out_b} connected primary 1920x1080+0+0" not in query:
        problems.append(f"{out_b} (DMD B) is not primary at +0+0")
    if f"{out_a} connected 1920x1080+1920+0" not in query \
            and f"{out_a} connected primary 1920x1080+1920+0" not in query:
        problems.append(f"{out_a} (DMD A) is not at +1920+0")
    if problems:
        raise RuntimeError("display validation failed: " + "; ".join(problems))
    log.info("Display validated: 3840x1080, %s left (B, primary), %s right (A)",
             out_b, out_a)


def _cleanup_step(description: str, action) -> None:
    try:
        action()
    except Exception as exc:
        log.warning("Cleanup (%s): %s", description, exc)


def main() -> int:
    # logging
    run_dir = create_run_directory()
    setup_logging(run_dir)
    log.info("Run directory: %s", run_dir)
    log.info("Git: %s", git_hash())

    from dmdcontrol.dmd.dlpc900 import DLPC900, load_from_config

    # dmds
    dmd_a, dmd_b = load_from_config()
    dlpc_a = DLPC900(dmd_a)
    dlpc_b = DLPC900(dmd_b)
    try:
        # Get dmds up
        wake_dmds(dlpc_a, dlpc_b)
        # Setup xorg display and validate
        setup_displays()
        validate_display()
        log.info("Display chunk complete: bring-up and validation succeeded")

        
        return 0
    finally:
        for name, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            _cleanup_step(f"DMD {name} close", dlpc.close)

if __name__ == "__main__":
    sys.exit(main())