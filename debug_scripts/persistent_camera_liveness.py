#!/usr/bin/env python3
"""
DVXplorer same-handle liveness probe.

Purpose:
- No DMD.
- No triggers.
- Open the camera once.
- Capture several event windows from the same camera handle.

Use this after a physical camera replug when testing whether close/reopen is
what poisons useful optical response.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dmdcontrol.camera.runs import _write_grayscale_png


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
        description="Open a DVXplorer once and capture multiple same-handle liveness windows.")
    parser.add_argument(
        "--prestate",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pre-run state metadata to include in stats.json; repeat for multiple fields.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/camera"),
        help="Parent output directory.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Output directory name. Default uses persistent_liveness_<timestamp>.",
    )
    parser.add_argument(
        "--windows",
        type=positive_int,
        default=5,
        help="Number of same-handle capture windows.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=positive_float,
        default=2.0,
        help="Duration of each capture window.",
    )
    parser.add_argument(
        "--gap-seconds",
        type=nonnegative_float,
        default=1.0,
        help="Delay between capture windows.",
    )
    parser.add_argument(
        "--drain-seconds",
        type=nonnegative_float,
        default=0.5,
        help="Initial stale-batch drain time after opening the camera.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=9,
        help="Contrast threshold for ON/OFF, usually 0-17.",
    )
    parser.add_argument(
        "--skip-threshold",
        action="store_true",
        default=False,
        help="Do not call setContrastThresholdOn/Off.",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=99.5,
        help="Percentile used for PGM normalization.",
    )
    return parser


def _monotonic_seconds() -> float:
    return time.time()


def event_value(event, name: str):
    attr = getattr(event, name)
    return attr() if callable(attr) else attr


def _batch_time_range_us(batch):
    try:
        return int(batch.getLowestTime()), int(batch.getHighestTime())
    except Exception:
        return None


def save_pgm(path: Path, accum: np.ndarray, *, percentile: float) -> None:
    img = np.log1p(accum.astype(np.float32))
    nonzero = img[img > 0]
    if nonzero.size:
        vmax = float(np.percentile(nonzero, percentile))
        if not math.isfinite(vmax) or vmax <= 0:
            vmax = float(nonzero.max())
        if vmax > 0:
            img = np.clip(img / vmax, 0, 1)
    img = (img * 255).astype(np.uint8)

    height, width = img.shape
    with path.open("wb") as handle:
        handle.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        handle.write(img.tobytes())


def drain_camera(camera, seconds: float) -> dict[str, int]:
    deadline = _monotonic_seconds() + seconds
    batches = 0
    events = 0
    while _monotonic_seconds() < deadline:
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


def capture_window(
    camera,
    label: str,
    out_dir: Path,
    *,
    seconds: float,
    percentile: float,
) -> dict:
    width, height = map(int, camera.getEventResolution())
    accum = np.zeros((height, width), dtype=np.uint32)

    total = 0
    on = 0
    off = 0
    batches = 0
    none_count = 0
    first_ts = None
    last_ts = None
    wall_bins = [0 for _ in range(max(1, math.ceil(seconds)))]

    print(f"\n=== {label} ===")
    print("Move laser/flashlight/diffuse spot during this window.")

    window_start = _monotonic_seconds()
    deadline = window_start + seconds
    while True:
        now = _monotonic_seconds()
        if now >= deadline:
            break

        batch = camera.getNextEventBatch()
        if batch is None:
            none_count += 1
            time.sleep(0.001)
            continue

        batches += 1
        batch_len = None
        try:
            batch_len = len(batch)
        except TypeError:
            pass
        if batch_len is not None:
            total += batch_len
            bin_index = min(int(now - window_start), len(wall_bins) - 1)
            wall_bins[bin_index] += batch_len

        time_range = _batch_time_range_us(batch)
        if time_range is not None:
            lo, hi = time_range
            first_ts = lo if first_ts is None else min(first_ts, lo)
            last_ts = hi if last_ts is None else max(last_ts, hi)

        for event in batch:
            try:
                x = int(event_value(event, "x"))
                y = int(event_value(event, "y"))
                polarity = bool(event_value(event, "polarity"))
            except Exception:
                continue

            if polarity:
                on += 1
            else:
                off += 1

            if 0 <= x < width and 0 <= y < height:
                accum[y, x] += 1

    camera_span_s = None
    if first_ts is not None and last_ts is not None:
        camera_span_s = (last_ts - first_ts) / 1_000_000.0

    pgm_path = out_dir / f"{label}.pgm"
    png_path = out_dir / f"{label}.png"
    npy_path = out_dir / f"{label}.npy"
    save_pgm(pgm_path, accum, percentile=percentile)
    _write_grayscale_png(png_path, accum)
    np.save(npy_path, accum)

    stats = {
        "label": label,
        "seconds": seconds,
        "events": int(total),
        "on": int(on),
        "off": int(off),
        "on_fraction": float(on / total) if total else None,
        "batches": int(batches),
        "none_count": int(none_count),
        "nonzero_pixels": int(np.count_nonzero(accum)),
        "max_pixel": int(accum.max()) if accum.size else 0,
        "wall_second_event_bins": [int(value) for value in wall_bins],
        "first_ts": first_ts,
        "last_ts": last_ts,
        "camera_span_s": camera_span_s,
        "pgm": str(pgm_path),
        "png": str(png_path),
        "npy": str(npy_path),
    }
    print(json.dumps(stats, indent=2))
    return stats


def _apply_threshold(camera, threshold: int) -> None:
    for name in ("setContrastThresholdOn", "setContrastThresholdOff"):
        method = getattr(camera, name, None)
        if callable(method):
            method(threshold)


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


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import dv_processing as dv

    output_name = args.name or f"persistent_liveness_{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = args.output_root / output_name
    out_dir.mkdir(parents=True, exist_ok=True)

    print("dv:", getattr(dv, "__version__", "unknown"), getattr(dv, "__file__", None))
    descriptors = dv.io.camera.discover()
    print("discovered:", len(descriptors))
    if not descriptors:
        raise SystemExit("No camera discovered")

    open_count = 0
    camera = dv.io.camera.open(descriptors[0])
    open_count += 1
    try:
        print("opened:", camera.getCameraName() if hasattr(camera, "getCameraName") else type(camera))
        print("resolution:", tuple(camera.getEventResolution()))

        if not args.skip_threshold:
            _apply_threshold(camera, args.threshold)

        drain_stats = drain_camera(camera, args.drain_seconds)
        print("drain:", json.dumps(drain_stats))

        windows = []
        for index in range(1, args.windows + 1):
            label = f"window_{index:02d}_same_handle"
            windows.append(
                capture_window(
                    camera,
                    label,
                    out_dir,
                    seconds=args.duration_seconds,
                    percentile=args.percentile,
                ))
            if index < args.windows and args.gap_seconds > 0:
                time.sleep(args.gap_seconds)

        stats = {
            "summary": {
                "prestate": parse_prestate(args.prestate),
                "camera_opens": open_count,
                "output_dir": str(out_dir),
                "windows": args.windows,
                "duration_seconds": args.duration_seconds,
                "gap_seconds": args.gap_seconds,
                "drain_seconds": args.drain_seconds,
                "threshold": args.threshold,
                "threshold_applied": not args.skip_threshold,
                "drain": drain_stats,
            },
            "windows": windows,
        }
        stats_path = out_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

        print("\nOUT:", out_dir)
        print("stats:", stats_path)
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
