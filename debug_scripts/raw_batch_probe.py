#!/usr/bin/env python3
"""
Minimal DVXplorer raw event-batch liveness probe.

Purpose:
- No DMD.
- No triggers.
- No AEDAT4.
- No PNG/image generation.
- No accumulator.
- Open the camera once and report raw getNextEventBatch() delivery by wall-time bin.
"""

from __future__ import annotations

import argparse
import json
import math
import time


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Open a DVXplorer once and report raw getNextEventBatch() liveness.")
    parser.add_argument(
        "--prestate",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pre-run state metadata to echo into logs; repeat for multiple fields.",
    )
    parser.add_argument("--windows", type=positive_int, default=3)
    parser.add_argument(
        "--duration",
        "--duration-seconds",
        dest="duration_seconds",
        type=positive_float,
        default=8.0,
        help="Duration of each capture window.",
    )
    parser.add_argument(
        "--gap",
        "--gap-seconds",
        dest="gap_seconds",
        type=nonnegative_float,
        default=1.0,
        help="Delay between capture windows.",
    )
    parser.add_argument(
        "--defaults",
        "--set-dvxplorer-defaults",
        dest="set_dvxplorer_defaults",
        action="store_true",
        default=False,
        help="Set threshold 9/9, VARIABLE_5000, global hold true, and global reset false when available.",
    )
    parser.add_argument(
        "--camera-open-method",
        choices=["open", "dvxplorer"],
        default="open",
        help="Use dv.io.camera.open() or dv.io.camera.DVXplorer().",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=9,
        help="Threshold used with --defaults.",
    )
    return parser


def _monotonic_seconds() -> float:
    return time.monotonic()


def event_count(batch) -> int:
    try:
        return len(batch)
    except TypeError:
        return sum(1 for _ in batch)


def ts_range(batch):
    try:
        return int(batch.getLowestTime()), int(batch.getHighestTime())
    except Exception:
        return None, None


def call_if_available(obj, name: str, *args) -> None:
    method = getattr(obj, name, None)
    if callable(method):
        method(*args)
        print(f"{name}{args}: OK")
    else:
        print(f"{name}: unavailable")


def apply_defaults(dv, camera, threshold: int) -> None:
    call_if_available(camera, "setContrastThresholdOn", threshold)
    call_if_available(camera, "setContrastThresholdOff", threshold)

    dvxplorer = getattr(dv.io.camera, "DVXplorer", None)
    readout = getattr(dvxplorer, "ReadoutFPS", None)
    if readout is not None and hasattr(readout, "VARIABLE_5000"):
        call_if_available(camera, "setReadoutFPS", readout.VARIABLE_5000)
    else:
        print("setReadoutFPS: unavailable")

    call_if_available(camera, "setGlobalHold", True)
    call_if_available(camera, "setGlobalReset", False)


def open_camera(dv, method: str):
    if method == "open":
        print("open method: dv.io.camera.open()")
        return dv.io.camera.open()

    constructor = getattr(dv.io.camera, "DVXplorer", None)
    if not callable(constructor):
        raise SystemExit("dv.io.camera.DVXplorer is not available in this environment")
    print("open method: dv.io.camera.DVXplorer()")
    return constructor()


def parse_prestate(values: list[str]) -> dict:
    fields = {}
    notes = []
    for value in values:
        if "=" not in value:
            notes.append(value)
            continue
        key, parsed = value.split("=", 1)
        key = key.strip()
        if key:
            fields[key] = parsed.strip()
        else:
            notes.append(value)
    return {"fields": fields, "notes": notes}


def capture_window(camera, label: str, seconds: float) -> dict:
    wall_bins = [0 for _ in range(max(1, math.ceil(seconds)))]
    batches = 0
    none_count = 0
    total = 0
    first_ts = None
    last_ts = None

    start = _monotonic_seconds()
    deadline = start + seconds

    while True:
        now = _monotonic_seconds()
        if now >= deadline:
            break

        batch = camera.getNextEventBatch()
        if batch is None:
            none_count += 1
            time.sleep(0.001)
            continue

        batch_len = event_count(batch)
        batches += 1
        total += batch_len

        bin_index = min(int(now - start), len(wall_bins) - 1)
        wall_bins[bin_index] += batch_len

        lo, hi = ts_range(batch)
        if lo is not None:
            first_ts = lo if first_ts is None else min(first_ts, lo)
            last_ts = hi if last_ts is None else max(last_ts, hi)

    camera_span_s = None
    if first_ts is not None and last_ts is not None:
        camera_span_s = (last_ts - first_ts) / 1_000_000.0

    result = {
        "label": label,
        "wall_seconds": seconds,
        "events": total,
        "batches": batches,
        "none_count": none_count,
        "wall_second_event_bins": wall_bins,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "camera_span_s": camera_span_s,
    }

    print(json.dumps(result, indent=2))
    return result


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import dv_processing as dv

    run_metadata = {
        "prestate": parse_prestate(args.prestate),
        "camera_open_method": args.camera_open_method,
        "set_dvxplorer_defaults": args.set_dvxplorer_defaults,
        "threshold": args.threshold,
        "windows": args.windows,
        "duration_seconds": args.duration_seconds,
        "gap_seconds": args.gap_seconds,
    }
    print("RUN_METADATA")
    print(json.dumps(run_metadata, indent=2))

    print("dv_processing:", getattr(dv, "__version__", "unknown"))
    print("dv_processing file:", getattr(dv, "__file__", None))
    print("discover:", dv.io.camera.discover())

    camera = open_camera(dv, args.camera_open_method)
    try:
        print("camera:", camera.getCameraName() if hasattr(camera, "getCameraName") else type(camera))
        print("type:", type(camera))
        print("resolution:", tuple(camera.getEventResolution()))
        print("isRunning:", camera.isRunning() if hasattr(camera, "isRunning") else "unknown")
        print(
            "event stream:",
            camera.isEventStreamAvailable() if hasattr(camera, "isEventStreamAvailable") else "unknown",
        )

        if args.set_dvxplorer_defaults:
            apply_defaults(dv, camera, args.threshold)

        results = []
        for index in range(1, args.windows + 1):
            print(f"\n=== window {index} ===")
            print("Move flashlight/laser/stimulus continuously now.")
            results.append(capture_window(camera, f"window_{index:02d}", args.duration_seconds))
            if index < args.windows and args.gap_seconds > 0:
                time.sleep(args.gap_seconds)

        print("\nSUMMARY")
        print(json.dumps(results, indent=2))
        return 0
    finally:
        try:
            del camera
        except Exception:
            pass
        import gc
        gc.collect()


if __name__ == "__main__":
    raise SystemExit(run())
