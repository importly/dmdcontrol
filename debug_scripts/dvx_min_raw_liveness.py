#!/usr/bin/env python3
"""
Minimal DVXplorer raw-batch liveness probe.

Purpose:
- Open one DVXplorer through dv_processing.
- Optionally apply the DV-view-style settings block.
- Poll getNextEventBatch() across repeated same-handle windows.
- Save only JSON summaries.

No image writing. No AEDAT4. No accumulator. No trigger logic.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import dv_processing as dv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--gap", type=float, default=1.0)
    parser.add_argument("--dv-view-defaults", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("runs/dvx_min_raw_liveness"))
    return parser


def call0(obj, name: str):
    method = getattr(obj, name, None)
    if not callable(method):
        return None
    try:
        return method()
    except Exception as exc:
        return f"ERROR: {exc!r}"


def call_setting(camera, name: str, *args):
    method = getattr(camera, name, None)
    if not callable(method):
        return {"method": name, "ok": False, "reason": "unavailable"}

    try:
        method(*args)
        return {"method": name, "ok": True, "args": [repr(arg) for arg in args]}
    except Exception as exc:
        return {"method": name, "ok": False, "reason": repr(exc)}


def resolution_tuple(camera):
    try:
        resolution = camera.getEventResolution()
    except Exception as exc:
        return f"ERROR: {exc!r}"

    if hasattr(resolution, "width") and hasattr(resolution, "height"):
        return [int(resolution.width), int(resolution.height)]

    try:
        width, height = resolution
        return [int(width), int(height)]
    except Exception:
        return repr(resolution)


def camera_info(camera):
    return {
        "type": f"{type(camera).__module__}.{type(camera).__name__}",
        "camera_name": call0(camera, "getCameraName"),
        "isConnected": call0(camera, "isConnected"),
        "isRunning": call0(camera, "isRunning"),
        "event_stream_available": call0(camera, "isEventStreamAvailable"),
        "event_resolution": resolution_tuple(camera),
    }


def discover_descriptors():
    try:
        return list(dv.io.camera.discover())
    except Exception:
        return []


def open_first_camera():
    descriptors = discover_descriptors()

    if descriptors:
        camera = dv.io.camera.open(descriptors[0])
    else:
        camera = dv.io.camera.open()

    return camera, descriptors


def apply_dv_view_defaults(camera):
    """
    Name is intentional: these are the settings copied from DV-view/C++-style testing,
    not mentor/legacy settings.
    """
    results = [
        call_setting(camera, "setContrastThresholdOn", 9),
        call_setting(camera, "setContrastThresholdOff", 9),
    ]

    dvxplorer = getattr(dv.io.camera, "DVXplorer", None)
    readout_enum = getattr(dvxplorer, "ReadoutFPS", None)
    variable_5000 = getattr(readout_enum, "VARIABLE_5000", None) if readout_enum else None

    if variable_5000 is None:
        results.append({
            "method": "setReadoutFPS",
            "ok": False,
            "reason": "DVXplorer.ReadoutFPS.VARIABLE_5000 unavailable",
        })
    else:
        results.append(call_setting(camera, "setReadoutFPS", variable_5000))

    results.append(call_setting(camera, "setGlobalHold", True))
    results.append(call_setting(camera, "setGlobalReset", False))

    return results


def batch_len(batch) -> int:
    try:
        return int(len(batch))
    except TypeError:
        return sum(1 for _ in batch)


def batch_time_range_us(batch):
    try:
        return int(batch.getLowestTime()), int(batch.getHighestTime())
    except Exception:
        return None


def capture_window(camera, label: str, duration: float):
    wall_bins = [0 for _ in range(max(1, math.ceil(duration)))]

    stats = {
        "label": label,
        "duration_s": duration,
        "events": 0,
        "batches": 0,
        "none_count": 0,
        "wall_second_event_bins": wall_bins,
        "first_ts": None,
        "last_ts": None,
        "camera_span_s": None,
        "isRunning_before": call0(camera, "isRunning"),
        "isRunning_after": None,
    }

    start = time.monotonic()
    deadline = start + duration

    while time.monotonic() < deadline:
        batch_wall_time = time.monotonic()
        batch = camera.getNextEventBatch()

        if batch is None:
            stats["none_count"] += 1
            time.sleep(0.001)
            continue

        n_events = batch_len(batch)
        stats["events"] += n_events
        stats["batches"] += 1

        bin_index = min(int(batch_wall_time - start), len(wall_bins) - 1)
        wall_bins[bin_index] += n_events

        time_range = batch_time_range_us(batch)
        if time_range is not None:
            lo, hi = time_range
            stats["first_ts"] = lo if stats["first_ts"] is None else min(stats["first_ts"], lo)
            stats["last_ts"] = hi if stats["last_ts"] is None else max(stats["last_ts"], hi)

    elapsed = time.monotonic() - start
    stats["elapsed_s"] = elapsed
    stats["events_per_s"] = stats["events"] / elapsed if elapsed > 0 else None
    stats["isRunning_after"] = call0(camera, "isRunning")

    if stats["first_ts"] is not None and stats["last_ts"] is not None:
        stats["camera_span_s"] = (stats["last_ts"] - stats["first_ts"]) / 1_000_000.0

    print(json.dumps(stats, indent=2))
    return stats


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()

    if args.windows <= 0:
        raise SystemExit("--windows must be positive")
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    if args.gap < 0:
        raise SystemExit("--gap must be nonnegative")

    run_dir = args.out / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    camera = None

    try:
        camera, descriptors = open_first_camera()

        metadata = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "argv": sys.argv,
            "prestate": os.environ.get("DVX_PRESTATE", ""),
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "dv_processing_version": getattr(dv, "__version__", "unknown"),
            "dv_processing_file": getattr(dv, "__file__", None),
            "dv_view_defaults": bool(args.dv_view_defaults),
            "descriptors": [repr(desc) for desc in descriptors],
            "camera_before_settings": camera_info(camera),
        }

        settings_results = []
        if args.dv_view_defaults:
            settings_results = apply_dv_view_defaults(camera)

        metadata["settings_results"] = settings_results
        metadata["camera_after_settings"] = camera_info(camera)

        print("RUN_DIR:", run_dir.resolve())
        print(json.dumps(metadata, indent=2))
        write_json(run_dir / "metadata.json", metadata)

        results = []
        for index in range(1, args.windows + 1):
            label = f"window_{index:02d}"
            print(f"\n=== {label} ===")
            results.append(capture_window(camera, label, args.duration))

            if index < args.windows and args.gap > 0:
                time.sleep(args.gap)

        summary = {
            "run_dir": str(run_dir),
            "metadata": metadata,
            "results": results,
        }

        write_json(run_dir / "summary.json", summary)
        print("\nSUMMARY_JSON:", (run_dir / "summary.json").resolve())
        return 0

    finally:
        camera = None
        gc.collect()


if __name__ == "__main__":
    raise SystemExit(main())
