from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import datetime
from math import ceil
from pathlib import Path

import numpy as np
from rich.logging import RichHandler

from dmdcontrol.laser import Laser
from dmdcontrol.runtime import PairRig, build_count_static_sequence
from dmdcontrol.utils import CONFIG, CONSOLE, WORKSPACE
from dmdcontrol.utils.config import CONFIG_PATH
from dmdcontrol.utils.stop import Stopped, install as stop_on_signals

log = logging.getLogger("main")
log.setLevel(CONFIG.log_level.upper())


def create_run_directory() -> Path:
    root = WORKSPACE / CONFIG.Run.output_root
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
    level = CONFIG.log_level.upper()
    console_handler = RichHandler(
        console=CONSOLE,  # shared with the progress bars, so log lines print above them
        show_path=False, rich_tracebacks=True, markup=False,
        omit_repeated_times=False, log_time_format="%H:%M:%S",
        level=level,
    )
    console_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    file_handler = logging.FileHandler(run_dir / "run.log")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [console_handler, file_handler]


def run_count(rig: PairRig, run_dir: Path) -> None:
    """A counts, B static dot; frames, contact sheet and the raw recording go to run_dir."""
    sequence = build_count_static_sequence()
    count = CONFIG.Run.Count
    log.info("Recipe: counts %d..%d | %d frames per cycle | %d cycles = %d frames | %d leader vsyncs",
             count.start, count.end, len(sequence.frames), count.cycles,
             count.cycles * len(sequence.frames), sequence.leader_vsyncs)

    capture = rig.play(sequence, count.cycles)
    np.save(run_dir / "triggers.npy", capture.triggers)
    np.save(run_dir / "events.npy", capture.events)

    frames = rig.camera.accumulate(capture.semantic, capture.events)
    rig.camera.save(frames, run_dir / "frames", save_as_png=True)
    rig.camera.contact_sheet(frames, run_dir / "contact_sheet.png", (20, ceil(len(frames) / 20)))
    if capture.dropped:
        log.critical("%d frame(s) dropped during semantic display: count/trigger alignment is off for this run",
                     capture.dropped)
    else:
        log.info("0 frames dropped during semantic display (count/trigger alignment intact)")


def main() -> int:
    stop_on_signals()
    run_dir = create_run_directory()
    setup_logging(run_dir)
    log.info("Run directory: %s", run_dir)
    log.info("Git: %s", git_hash())
    log.info("Config: %s", CONFIG_PATH)
    shutil.copy(CONFIG_PATH, run_dir / "config.yaml")
    log.info("Mode: %s", CONFIG.Run.mode)

    try:
        with Laser(), PairRig() as rig:
            if CONFIG.Run.mode == "count":
                run_count(rig, run_dir)
            else:
                from collect import collect_kernels  # torch is only needed here
                collect_kernels(rig, run_dir)
        return 0
    except Stopped as exc:
        log.warning("Stopped by %s", exc)
        return 128 + exc.signum
    except Exception as exc:
        log.exception("%s run failed: %s", CONFIG.Run.mode, exc)
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run what Run.mode in the config says.")
    parser.add_argument("--config", type=Path, help="config file to use instead of config.yaml")
    parser.parse_args()
    sys.exit(main())
