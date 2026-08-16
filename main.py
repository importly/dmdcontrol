from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dmdcontrol.camera import Camera
from dmdcontrol.dmd import DLPC900, load_from_config
from dmdcontrol.patterns import _decimal_number_display_masks, generate_dot_frame
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
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"
    )
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [stream_handler, file_handler]


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
        

def generate_fm_k_sequence(length: int):
    """Generate a sequence of (fm, k) pairs for testing."""
    # Feature maps
    fms = _decimal_number_display_masks(
        numbers=range(length),
        width=300,
        height=300,
        size_px=30
    )

    # Kernel
    k = generate_dot_frame()
    
    return fms, k


def main() -> int:
    # logging
    run_dir = create_run_directory()
    setup_logging(run_dir)
    log.info("Run directory: %s", run_dir)
    log.info("Git: %s", git_hash())
    
    # Generate the feature maps and kernels
    trial_length = 100
    fms, k = generate_fm_k_sequence(trial_length)

    # dmds
    dmd_a, dmd_b = load_from_config()
    dlpc_a = DLPC900(dmd_a)
    dlpc_b = DLPC900(dmd_b)
    
    # Camera setup
    camera = Camera()
    
    try:
        # Get dmds up
        wake_dmds(dlpc_a, dlpc_b)
        # Setup xorg display and validate
        setup_displays()
        validate_display()
        log.info("Display chunk complete: bring-up and validation succeeded")
        
        # Start recording
        triggers, events = camera.record(trigger_count=2*trial_length)
        
        # Process events
        frames = camera.accumulate(triggers, events)
        
        # Save frames
        camera.save(frames, folder=run_dir / 'frames', save_as_jpg=True)
        camera.contact_sheet(frames, folder=run_dir / 'contact_sheet')
        
        return 0
    except Exception as exc:
        log.exception("Display chunk failed: %s", exc)
        return 1
    finally:
        for name, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            _cleanup_step(f"DMD {name} close", dlpc_a.close)
            _cleanup_step(f"DMD {name} close", dlpc_b.close)

if __name__ == "__main__":
    sys.exit(main())