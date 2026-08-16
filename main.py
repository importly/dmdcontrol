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

    from dmdcontrol.dmd.dlpc900 import DLPC900, load_from_config

    # dmds
    dmd_a, dmd_b = load_from_config()
    dlpc_a = DLPC900(dmd_a)
    dlpc_b = DLPC900(dmd_b)
    engine = None
    coordinator = None
    
    # Camera setup
    camera = Camera()
    
    try:
        # Get dmds up
        wake_dmds(dlpc_a, dlpc_b)
        # Setup xorg display and validate
        setup_displays()
        validate_display()

        from dmdcontrol.patterns.paired import PairedPatternEngine
        from dmdcontrol.runtime.display_sequence import build_count_static_sequence
        from dmdcontrol.runtime.pair_render import _start_pair_render_coordinator
        from dmdcontrol.runtime.video_pattern import (
            load_pattern_sequence,
            prepare_pair_controllers,
            start_loaded_pattern_sequences,
            verify_started_pattern_sequence,
        )

        # A counts, B static dot, setup sequence
        sequence = build_count_static_sequence()
        leader = sequence.startup_leader_metadata()
        cycles = int(RUN["cycles"])
        semantic_frames = cycles * len(sequence.frames)
        log.info("Recipe: counts %d..%d | %d frames per cycle | %d cycles = %d frames | %d leader vsyncs",
                 RUN["count_start"], RUN["count_end"], len(sequence.frames),
                 cycles, semantic_frames, leader["leader_vsyncs"])

        # hold the startup pair until the sequencers are running
        engine = PairedPatternEngine()
        coordinator = _start_pair_render_coordinator(
            engine,
            sequence.provider,
            startup_leader_pair=sequence.startup_pair,
            startup_leader_vsyncs=leader["leader_vsyncs"],
            semantic_frames=semantic_frames,
        )
        if not coordinator.wait_until_ready(timeout_s=2.0):
            raise RuntimeError("render coordinator did not become ready")

        # lut plans
        plan_a = sequence.lut_plan_a()
        plan_b = sequence.lut_plan_b()
        
        prepare_pair_controllers(
            dlpc_a, dlpc_b,
            entries_count_a=len(plan_a.entries),
            entries_count_b=len(plan_b.entries),
        )
        load_pattern_sequence(dlpc_a, plan_a.entries)
        load_pattern_sequence(dlpc_b, plan_b.entries)
        start_loaded_pattern_sequences(dlpc_a, dlpc_b, post_start_delay_s=0.0, verify=False)

        coordinator.release_semantic_frames()
        
        for name, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            hw = verify_started_pattern_sequence(dlpc, label=f"DMD {name}")
            log.info("DMD %s sequencer running in Video Pattern Mode (hw=%s)",
                     name, f"0x{hw:02X}" if hw is not None else "n/a")
        log.info("Displaying %d frames (%d leader + %d count)...",
                 leader["leader_vsyncs"] + semantic_frames, leader["leader_vsyncs"], semantic_frames)
        dropped_before = engine.dropped_frames  # stutters during DLPC setup are pre-display, ignore
        coordinator.join()
        dropped = engine.dropped_frames - dropped_before
        if dropped:
            log.critical("%d frame(s) dropped during display: count/trigger alignment is off for this run", dropped)
        log.info("Displayed %d frames, %d dropped; count chunk complete (%d cycles)",
                 leader["leader_vsyncs"] + semantic_frames, dropped, cycles)
        return 0
    except Exception as exc:
        log.exception("Display chunk failed: %s", exc)
        return 1
    finally:
        if coordinator is not None:
            _cleanup_step("render coordinator stop", coordinator.stop)
        for name, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            _cleanup_step(f"DMD {name} stop pattern display",
                          partial(dlpc.start_pattern_display, 0))
            _cleanup_step(f"DMD {name} restore video mode",
                          partial(dlpc.set_display_mode, 0))
            _cleanup_step(f"DMD {name} block-lock workaround",
                          dlpc.apply_block_lock_workaround)
            _cleanup_step(f"DMD {name} close", dlpc.close)
        if engine is not None:
            _cleanup_step("engine cleanup", engine.cleanup)

            _cleanup_step(f"DMD {name} close", dlpc_a.close)
            _cleanup_step(f"DMD {name} close", dlpc_b.close)

if __name__ == "__main__":
    sys.exit(main())
