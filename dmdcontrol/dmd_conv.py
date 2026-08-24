from __future__ import annotations

import logging
import os
import gc
import subprocess
import time
from datetime import datetime
from pathlib import Path
from functools import partial
from rich.logging import RichHandler
from logging.handlers import RotatingFileHandler
from math import ceil
from contextlib import contextmanager

import requests
import numpy as np

from dmdcontrol.camera import Camera, contact_sheet
from dmdcontrol.dmd import (
    DLPC900,
    load_from_config
)
from dmdcontrol.patterns import (
    PairedPatternEngine,
)
from dmdcontrol.runtime import (
    build_dynamic_fm_sequence,
    _start_pair_render_coordinator,
    load_pattern_sequence,
    prepare_pair_controllers,
    start_loaded_pattern_sequences,
    verify_started_pattern_sequence,
)
from dmdcontrol.utils import CONFIG, WORKSPACE

log = logging.getLogger("main")
log.setLevel(str(CONFIG.get("log_level", "INFO")).upper())

RUN = CONFIG.get("Run", {})
DMD_CFG = CONFIG.get("DMD", {})
DISPLAY_ID = ":0"


@contextmanager
def disable_gc():
    # Check if GC is already disabled to preserve that state
    was_enabled = gc.isenabled()
    if was_enabled:
        gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


def create_run_directory() -> Path:
    run_dir = WORKSPACE / f"{RUN.get("output_root", "data-collection-logs")}_{datetime.now():%Y%m%d-%H%M%S}"
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
    level = str(CONFIG.get("log_level", "INFO")).upper()
    # console_handler = RichHandler(
    #     show_path=False, rich_tracebacks=True, markup=True,
    #     omit_repeated_times=False, log_time_format="%H:%M:%S",
    #     level=level,
    # )
    # console_handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    file_handler = RotatingFileHandler(run_dir / "run.log", maxBytes=1024*1024, backupCount=5)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [file_handler]


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


def display_data(
    fm: np.ndarray,
    k: np.ndarray, 
    kernel_pos: bool = True,
    contact_sheet_path: Path | None = None,
    ) -> tuple[np.ndarray, np.ndarray] | int:

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

        # A counts, B static dot, setup sequence
        sequence = build_dynamic_fm_sequence(fm, k, kernel_pos=kernel_pos)
        leader = sequence.startup_leader_metadata()
        cycles = int(RUN["cycles"])
        semantic_frames = cycles * len(sequence.frames)
        log.info("Recipe: counts %d..%d | %d frames per cycle | %d cycles = %d frames | %d leader vsyncs",
                 RUN["count_start"], RUN["count_end"], len(sequence.frames),
                 cycles, semantic_frames, leader["vsyncs"])

        # hold the startup pair until the sequencers are running
        engine = PairedPatternEngine()
        coordinator = _start_pair_render_coordinator(
            engine,
            sequence.provider,
            startup_leader_pair=sequence.startup_pair,
            startup_leader_vsyncs=leader["vsyncs"],
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
        start_loaded_pattern_sequences(dlpc_a, dlpc_b, post_start_delay_s=0, verify=False)

        for name, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            hw = verify_started_pattern_sequence(dlpc, label=f"DMD {name}")
            log.info("DMD %s sequencer running in Video Pattern Mode (hw=%s)",
                     name, f"0x{hw:02X}" if hw is not None else "n/a")
        log.info("Displaying %d frames (%d leader + %d count)...",
                 leader["vsyncs"] + semantic_frames, leader["vsyncs"], semantic_frames)
        dropped_before = engine.dropped_frames  # stutters during DLPC setup are pre-display, ignore
        
        # with disable_gc():
        # Start display
        expected_triggers = semantic_frames + leader["vsyncs"] + 8
        log.info("leader vsyncs: %d (%d triggers) semantic frames: %d expected triggers: %d",
                leader["vsyncs"], leader["trigger_count"], semantic_frames, expected_triggers)
        log.info("starting display")

        coordinator.release_startup_leader()
        if not coordinator.wait_leader_done(timeout_s=5.0):
            raise RuntimeError("startup leader did not complete")

        camera.flush()
        coordinator.release_semantic_frames()
        triggers, events = camera.record(expected_triggers+2)

        if not coordinator.wait_semantic_frames_done(timeout_s=8.0):
            raise RuntimeError("semantic playback did not finish")
        coordinator.join()

        camera.camera.setEventsRunning(False)
        camera.camera.setDetectorRunning(False)
        camera.flush()
        dropped = engine.dropped_frames - dropped_before
        log.info("Displayed %d frames, %d dropped; count chunk complete (%d cycles)",
                 leader["vsyncs"] + semantic_frames, dropped, cycles)
        if dropped:
            log.critical("%d frame(s) dropped during display: count/trigger alignment is off for this run", dropped)
            return 0
        
        # Process and save results
        frames = camera.accumulate(triggers, events, semantic_frames//2)
        
        del camera
        
        if contact_sheet_path is not None:
            # camera.save(frames, contact_sheet_path.parent / 'frames', save_as_img=True)
            contact_sheet(frames, contact_sheet_path, (20,ceil(frames.shape[0]/20)))
            
            requests.put(
                'https://ntfy.sh/eodla',
                data=open(contact_sheet_path, 'rb'),
                headers={'Filename': contact_sheet_path.name, 'Title': 'Contact Sheet'},
            )
        
        fm_pos = frames[:frames.shape[0]//2]
        fm_neg = frames[frames.shape[0]//2:]
        return fm_pos, fm_neg
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





def dmd_conv(fm: np.ndarray, k: np.ndarray, save_sheet: bool, run_dir: Path | None) -> np.ndarray | int:
    # logging
    if run_dir is None:
        run_dir = create_run_directory()
    setup_logging(run_dir)
    log.info("Run directory: %s", run_dir)
    log.debug("Git: %s", git_hash())
    
    # Positive Kernel
    while True:
        ret = display_data(fm, k, True, run_dir / Path("contact_sheet_loop_0.jpg") if save_sheet else None)
        if isinstance(ret, tuple):
            k_pos_fm_pos, k_pos_fm_neg = ret
            break
        elif ret == 0:
            log.warning("Retrying...")
        else:
            return ret
            
    # Negative Kernel
    while True:
        ret = display_data(fm, k, False, run_dir / Path("contact_sheet_loop_1.jpg") if save_sheet else None)
        if isinstance(ret, tuple):
            k_neg_fm_pos, k_neg_fm_neg = ret
            break
        elif ret == 0:
            log.warning("Retrying...")
        else:
            return ret

    k_pos_fm_pos = (k_pos_fm_pos - k_pos_fm_pos.min()) / (k_pos_fm_pos.max() - k_pos_fm_pos.min())
    k_neg_fm_pos = (k_neg_fm_pos - k_neg_fm_pos.min()) / (k_neg_fm_pos.max() - k_neg_fm_pos.min())
    k_pos_fm_neg = (k_pos_fm_neg - k_pos_fm_neg.min()) / (k_pos_fm_neg.max() - k_pos_fm_neg.min())
    k_neg_fm_neg = (k_neg_fm_neg - k_neg_fm_neg.min()) / (k_neg_fm_neg.max() - k_neg_fm_neg.min())
    gamma = 1.5
    conv = k_pos_fm_pos**gamma - k_neg_fm_pos**gamma - k_pos_fm_neg**gamma + k_neg_fm_neg**gamma
    
    if save_sheet:
        contact_sheet(
            frames=conv, 
            save_path=run_dir / Path('contact_sheet_conv.jpg'), 
            grid_size=(20,ceil(conv.shape[0]/20)),
            )
                    
        requests.put(
            'https://ntfy.sh/eodla',
            data=open(run_dir / Path('contact_sheet_conv.jpg'), 'rb'),
            headers={'Filename': 'contact_sheet_conv.jpg', 'Title': 'Contact Sheet'},
        )

    return conv
