#!/usr/bin/env python3
"""
Minimal DVXplorer reopen repro.

Modes:
  same-handle:
    open camera once, drain once, capture multiple windows from same handle

  reopen:
    for each window, open camera, drain, capture one window, close handle

Writes per window:
  - .aedat4 raw event stream
  - _activity.png / _activity.pgm
  - _signed.png / _signed.pgm
  - summary.csv

Important:
  Do NOT gate capture windows on camera.isRunning().
  Some environments report false even when getNextEventBatch can still be used.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import dv_processing as dv
import numpy as np
from PIL import Image


def event_value(event, name: str):
    attr = getattr(event, name)
    return attr() if callable(attr) else attr


def run_cmd(cmd: list[str]) -> str:
    try:
        return subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
            check=False,
        ).stdout.strip()
    except Exception as exc:
        return f"failed: {exc}"


def apply_threshold(camera, threshold: int) -> None:
    for name in ("setContrastThresholdOn", "setContrastThresholdOff"):
        method = getattr(camera, name, None)
        if callable(method):
            method(threshold)


def drain_camera(camera, seconds: float) -> dict[str, int]:
    deadline = time.monotonic() + seconds
    batches = 0
    events = 0

    while time.monotonic() < deadline:
        batch = camera.getNextEventBatch()
        if batch is None:
            time.sleep(0.001)
            continue

        batches += 1
        try:
            events += len(batch)
        except TypeError:
            pass

    return {"drained_batches": batches, "drained_events": events}


def open_first_camera(threshold: int | None, drain_seconds: float):
    descriptors = dv.io.camera.discover()
    if not descriptors:
        raise RuntimeError("No camera discovered.")

    camera = dv.io.camera.open(descriptors[0])
    camera_name = camera.getCameraName()
    width, height = map(int, camera.getEventResolution())

    if threshold is not None:
        apply_threshold(camera, threshold)

    drain_stats = drain_camera(camera, drain_seconds)

    return camera, camera_name, width, height, drain_stats


def make_writer(path: Path, camera_name: str, width: int, height: int):
    config = dv.io.MonoCameraWriter.EventOnlyConfig(camera_name, (width, height))
    return dv.io.MonoCameraWriter(str(path), config)


def gamma_encode(norm: np.ndarray, gamma: float) -> np.ndarray:
    norm = np.clip(norm.astype(np.float64), 0.0, 1.0)
    return np.power(norm, 1.0 / gamma)


def make_activity_image(on_counts: np.ndarray, off_counts: np.ndarray, gamma: float):
    activity = on_counts + off_counts
    max_activity = int(activity.max()) if activity.size else 0

    if max_activity == 0:
        return np.zeros(activity.shape, dtype=np.uint8), 0

    norm = np.log1p(activity.astype(np.float64)) / math.log1p(max_activity)
    img = np.rint(gamma_encode(norm, gamma) * 255.0).astype(np.uint8)
    return img, max_activity


def make_signed_image(on_counts: np.ndarray, off_counts: np.ndarray, gamma: float):
    signed = on_counts.astype(np.int64) - off_counts.astype(np.int64)
    max_abs = int(np.max(np.abs(signed))) if signed.size else 0

    if max_abs == 0:
        return np.full(signed.shape, 127, dtype=np.uint8), 0

    mag = np.log1p(np.abs(signed).astype(np.float64)) / math.log1p(max_abs)
    mag = gamma_encode(mag, gamma)

    signed_norm = 0.5 + 0.5 * np.sign(signed) * mag
    img = np.rint(np.clip(signed_norm, 0.0, 1.0) * 255.0).astype(np.uint8)
    return img, max_abs


def save_gray(path: Path, img: np.ndarray) -> None:
    Image.fromarray(img, mode="L").save(path)


def batch_time_range_us(batch):
    try:
        return int(batch.getLowestTime()), int(batch.getHighestTime())
    except Exception:
        return None


def capture_window(
    camera,
    label: str,
    out_dir: Path,
    *,
    seconds: float,
    camera_name: str,
    width: int,
    height: int,
    gamma: float,
) -> dict:
    print(f"\n=== {label} ===")
    is_running = getattr(camera, "isRunning", lambda: "unknown")()
    print(f"isRunning diagnostic before window: {is_running}")

    aedat4_path = out_dir / f"{label}.aedat4"
    activity_png = out_dir / f"{label}_activity.png"
    activity_pgm = out_dir / f"{label}_activity.pgm"
    signed_png = out_dir / f"{label}_signed.png"
    signed_pgm = out_dir / f"{label}_signed.pgm"

    on_counts = np.zeros((height, width), dtype=np.uint64)
    off_counts = np.zeros((height, width), dtype=np.uint64)

    stats = {
        "events": 0,
        "on": 0,
        "off": 0,
        "batches": 0,
        "none_count": 0,
        "out_of_bounds": 0,
        "first_ts": None,
        "last_ts": None,
    }

    writer = make_writer(aedat4_path, camera_name, width, height)

    start = time.monotonic()
    deadline = start + seconds

    try:
        # Critical: do NOT gate on camera.isRunning().
        while time.monotonic() < deadline:
            batch = camera.getNextEventBatch()

            if batch is None:
                stats["none_count"] += 1
                time.sleep(0.001)
                continue

            stats["batches"] += 1
            writer.writeEvents(batch)

            tr = batch_time_range_us(batch)
            if tr is not None:
                lo, hi = tr
                stats["first_ts"] = lo if stats["first_ts"] is None else min(stats["first_ts"], lo)
                stats["last_ts"] = hi if stats["last_ts"] is None else max(stats["last_ts"], hi)

            for event in batch:
                try:
                    x = int(event_value(event, "x"))
                    y = int(event_value(event, "y"))
                    polarity = bool(event_value(event, "polarity"))
                except Exception:
                    continue

                stats["events"] += 1

                if polarity:
                    stats["on"] += 1
                else:
                    stats["off"] += 1

                if not (0 <= x < width and 0 <= y < height):
                    stats["out_of_bounds"] += 1
                    continue

                if polarity:
                    on_counts[y, x] += 1
                else:
                    off_counts[y, x] += 1

    finally:
        writer = None
        gc.collect()

    elapsed = time.monotonic() - start

    activity = on_counts + off_counts
    signed = on_counts.astype(np.int64) - off_counts.astype(np.int64)

    activity_img, max_activity = make_activity_image(on_counts, off_counts, gamma)
    signed_img, max_abs_signed = make_signed_image(on_counts, off_counts, gamma)

    save_gray(activity_png, activity_img)
    save_gray(activity_pgm, activity_img)
    save_gray(signed_png, signed_img)
    save_gray(signed_pgm, signed_img)

    row = {
        "label": label,
        "seconds": seconds,
        "elapsed_s": f"{elapsed:.3f}",
        "camera_name": camera_name,
        "resolution": f"{width}x{height}",
        "events": int(stats["events"]),
        "events_per_s": f"{stats['events'] / elapsed:.2f}" if elapsed > 0 else "",
        "on": int(stats["on"]),
        "off": int(stats["off"]),
        "on_fraction": float(stats["on"] / stats["events"]) if stats["events"] else None,
        "batches": int(stats["batches"]),
        "none_count": int(stats["none_count"]),
        "out_of_bounds": int(stats["out_of_bounds"]),
        "nonzero_activity_pixels": int(np.count_nonzero(activity)),
        "nonzero_signed_pixels": int(np.count_nonzero(signed)),
        "max_activity_pixel_events": int(max_activity),
        "max_abs_signed_pixel_events": int(max_abs_signed),
        "first_ts": stats["first_ts"],
        "last_ts": stats["last_ts"],
        "aedat4": str(aedat4_path),
        "activity_png": str(activity_png),
        "activity_pgm": str(activity_pgm),
        "signed_png": str(signed_png),
        "signed_pgm": str(signed_pgm),
    }

    print(json.dumps(row, indent=2))
    return row


def write_environment(out_dir: Path, args) -> None:
    path = out_dir / "environment.txt"

    with path.open("w", encoding="utf-8") as f:
        f.write(f"timestamp: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"argv: {' '.join(sys.argv)}\n")
        f.write(f"python: {sys.version.replace(chr(10), ' ')}\n")
        f.write(f"platform: {platform.platform()}\n")
        f.write(f"dv_processing_version: {getattr(dv, '__version__', 'unknown')}\n")
        f.write(f"dv_processing_file: {getattr(dv, '__file__', 'unknown')}\n")
        f.write(f"mode: {args.mode}\n")
        f.write(f"duration: {args.duration}\n")
        f.write(f"cycles: {args.cycles}\n")
        f.write(f"pause: {args.pause}\n")
        f.write(f"drain: {args.drain}\n")
        f.write(f"threshold: {args.threshold}\n")
        f.write(f"gamma: {args.gamma}\n")

        f.write("\n--- dv.io.camera.discover() ---\n")
        try:
            f.write(str(dv.io.camera.discover()) + "\n")
        except Exception as exc:
            f.write(f"discover failed: {exc}\n")

        f.write("\n--- dv-list-devices ---\n")
        f.write(run_cmd(["dv-list-devices"]) + "\n")


def write_summary_csv(out_dir: Path, rows: list[dict]) -> Path:
    path = out_dir / "summary.csv"

    if not rows:
        return path

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["same-handle", "reopen"], required=True)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--drain", type=float, default=0.5)
    parser.add_argument("--threshold", type=int, default=9)
    parser.add_argument("--skip-threshold", action="store_true")
    parser.add_argument("--gamma", type=float, default=2.2)
    parser.add_argument("--out", type=Path, default=Path("runs/camera_reopen_repro"))
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.duration <= 0:
        raise ValueError("--duration must be positive")
    if args.cycles <= 0:
        raise ValueError("--cycles must be positive")
    if args.pause < 0:
        raise ValueError("--pause must be nonnegative")
    if args.drain < 0:
        raise ValueError("--drain must be nonnegative")
    if args.gamma <= 0:
        raise ValueError("--gamma must be positive")

    out_dir = args.out / f"{args.mode}_{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    write_environment(out_dir, args)

    rows = []
    threshold = None if args.skip_threshold else args.threshold

    if args.mode == "same-handle":
        camera = None
        try:
            camera, camera_name, width, height, drain_stats = open_first_camera(
                threshold=threshold,
                drain_seconds=args.drain,
            )
            print(f"Opened once: {camera_name}, resolution={width}x{height}")
            print("drain:", json.dumps(drain_stats))

            for i in range(1, args.cycles + 1):
                rows.append(
                    capture_window(
                        camera,
                        f"same_handle_{i:02d}",
                        out_dir,
                        seconds=args.duration,
                        camera_name=camera_name,
                        width=width,
                        height=height,
                        gamma=args.gamma,
                    )
                )

                if i < args.cycles and args.pause > 0:
                    time.sleep(args.pause)

        finally:
            camera = None
            gc.collect()

    else:
        for i in range(1, args.cycles + 1):
            camera = None
            try:
                camera, camera_name, width, height, drain_stats = open_first_camera(
                    threshold=threshold,
                    drain_seconds=args.drain,
                )
                print(f"Opened cycle {i}: {camera_name}, resolution={width}x{height}")
                print("drain:", json.dumps(drain_stats))

                rows.append(
                    capture_window(
                        camera,
                        f"reopen_{i:02d}",
                        out_dir,
                        seconds=args.duration,
                        camera_name=camera_name,
                        width=width,
                        height=height,
                        gamma=args.gamma,
                    )
                )

            finally:
                camera = None
                gc.collect()

            if i < args.cycles and args.pause > 0:
                time.sleep(args.pause)

    summary_path = write_summary_csv(out_dir, rows)

    print("\nOUT:", out_dir)
    print("summary:", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())