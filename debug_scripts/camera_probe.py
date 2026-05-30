#!/usr/bin/env python3
"""
DVXplorer positive-event optical probe.

Purpose:
- No DMD.
- No triggers.
- No AEDAT writer.
- Uses dmdcontrol camera USB reset helper, then reads live event batches from dv_processing.
- Accumulates ON / positive polarity events into one PNG.

Expected result:
- Move a laser pointer / bright spot across the camera view.
- Output image should show a bright trail/line if the camera is optically seeing the target plane.
"""

import argparse
import gc
import json
import math
import os
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dmdcontrol.camera.usb_reset import reset_camera_usb, run_power_cycle_command


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Camera-only DVXplorer positive-event accumulation probe"
    )
    parser.add_argument(
        "--duration-seconds",
        type=positive_float,
        default=5.0,
        help="Capture duration in seconds.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=9,
        help="Contrast threshold for ON/OFF, usually 0-17. Lower is more sensitive/noisier.",
    )
    parser.add_argument(
        "--drain-seconds",
        type=positive_float,
        default=0.5,
        help="Drain stale events before capture.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("runs/camera_probe"),
        help="Output directory.",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Optional output basename. Default uses timestamp.",
    )
    parser.add_argument(
        "--log-scale",
        action="store_true",
        default=True,
        help="Use log scaling for PNG visualization. Default true.",
    )
    parser.add_argument(
        "--linear-scale",
        action="store_true",
        help="Also save a linear-scaled PNG.",
    )
    parser.add_argument(
        "--percentile",
        type=float,
        default=99.5,
        help="Percentile used for image normalization.",
    )
    parser.add_argument(
        "--usb-reset",
        dest="usb_reset",
        action="store_true",
        default=False,
        help="Diagnostic: run a Linux USB device reset before opening the camera. Disabled by default.",
    )
    parser.add_argument(
        "--no-usb-reset",
        dest="usb_reset",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--power-cycle-command",
        default=None,
        help=(
            "Optional command run before camera open to power-cycle the USB port, "
            "for example: \"uhubctl -l 1-2 -p 3 -a cycle -d 2\". "
            "Defaults to DMD_CAMERA_POWER_CYCLE_COMMAND when set."
        ),
    )
    parser.add_argument(
        "--stream-rearm",
        action="store_true",
        default=False,
        help="Diagnostic: cycle the event stream off/on before capture. Disabled by default.",
    )
    return parser


def event_value(ev, name: str):
    attr = getattr(ev, name)
    return attr() if callable(attr) else attr


def write_png_gray8(path: Path, image_u8: np.ndarray) -> None:
    """
    Minimal dependency-free grayscale PNG writer.
    image_u8 must be 2D uint8.
    """
    if image_u8.ndim != 2:
        raise ValueError("image must be 2D")
    if image_u8.dtype != np.uint8:
        raise ValueError("image must be uint8")

    height, width = image_u8.shape

    raw = b"".join(
        b"\x00" + image_u8[y, :].tobytes()
        for y in range(height)
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(
        b"IHDR",
        struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0),
    )
    png += chunk(b"IDAT", zlib.compress(raw, level=6))
    png += chunk(b"IEND", b"")

    path.write_bytes(png)


def normalize_to_u8(accum: np.ndarray, *, log_scale: bool, percentile: float) -> np.ndarray:
    img = accum.astype(np.float32)

    if log_scale:
        img = np.log1p(img)

    nonzero = img[img > 0]
    if nonzero.size == 0:
        return np.zeros_like(img, dtype=np.uint8)

    vmax = float(np.percentile(nonzero, percentile))
    if not math.isfinite(vmax) or vmax <= 0:
        vmax = float(nonzero.max())
    if vmax <= 0:
        vmax = 1.0

    img = np.clip(img / vmax, 0.0, 1.0)
    return (img * 255.0).astype(np.uint8)


def try_call(obj, name: str, *args):
    fn = getattr(obj, name, None)
    if not callable(fn):
        print(f"[probe] {name} unavailable")
        return None

    try:
        out = fn(*args)
        print(f"[probe] {name}{args} -> OK")
        return out
    except Exception as e:
        print(f"[probe] {name}{args} -> ERROR: {e!r}")
        return None


def rearm_event_stream(capture, settle_s=0.05, drain_reads=10) -> None:
    try_call(capture, "setEventsRunning", False)
    if settle_s > 0:
        time.sleep(settle_s)
    try_call(capture, "setEventsRunning", True)
    for _ in range(max(0, int(drain_reads))):
        if hasattr(capture, "getNextEventBatch"):
            capture.getNextEventBatch()


def drain_events(capture, seconds: float) -> tuple[int, int]:
    deadline = time.time() + seconds
    batches = 0
    events = 0

    while time.time() < deadline:
        batch = capture.getNextEventBatch()
        if batch is None:
            time.sleep(0.001)
            continue

        batches += 1
        try:
            events += len(batch)
        except Exception:
            pass

    return batches, events


def run() -> int:
    args = build_parser().parse_args()
    import dv_processing as dv

    args.output_dir.mkdir(parents=True, exist_ok=True)

    basename = args.name
    if basename is None:
        basename = f"positive_probe_{time.strftime('%Y%m%d-%H%M%S')}"

    print("[probe] dv_processing:", dv)
    print("[probe] dv_processing version:", getattr(dv, "__version__", "unknown"))
    power_cycle_command = args.power_cycle_command or os.environ.get("DMD_CAMERA_POWER_CYCLE_COMMAND")
    print("[probe] power cycle:", run_power_cycle_command(power_cycle_command))
    print("[probe] usb reset:", reset_camera_usb(dv, enabled=args.usb_reset))

    descs = dv.io.camera.discover()
    print(f"[probe] discovered {len(descs)} camera(s)")
    for i, d in enumerate(descs):
        print(
            f"  [{i}] "
            f"model={getattr(d, 'cameraModel', None)} "
            f"serial={getattr(d, 'serialNumber', None)} "
            f"devAddress={getattr(d, 'devAddress', None)}"
        )

    if not descs:
        raise RuntimeError("No camera discovered")

    print("[probe] opening first camera")
    capture = dv.io.camera.open(descs[0])

    print("[probe] capture type:", type(capture))
    print("[probe] name:", capture.getCameraName() if hasattr(capture, "getCameraName") else "unknown")
    print("[probe] event stream:", capture.isEventStreamAvailable())
    print("[probe] trigger stream:", capture.isTriggerStreamAvailable() if hasattr(capture, "isTriggerStreamAvailable") else "unknown")
    print("[probe] running:", capture.isRunning())

    if not capture.isEventStreamAvailable():
        raise RuntimeError("Event stream unavailable")

    resolution = tuple(map(int, capture.getEventResolution()))
    width, height = resolution
    print("[probe] event resolution:", resolution)

    # Conservative baseline. Lower this to 6 only if the trail is too weak.
    try_call(capture, "setContrastThresholdOn", args.threshold)
    try_call(capture, "setContrastThresholdOff", args.threshold)
    if args.stream_rearm:
        rearm_event_stream(capture)

    try:
        print("[probe] getContrastThresholdOn:", capture.getContrastThresholdOn())
    except Exception:
        pass

    try:
        print("[probe] getContrastThresholdOff:", capture.getContrastThresholdOff())
    except Exception:
        pass

    print(f"[probe] draining stale events for {args.drain_seconds:.2f}s")
    drained_batches, drained_events = drain_events(capture, args.drain_seconds)
    print(f"[probe] drained batches={drained_batches}, events={drained_events}")

    accum_on = np.zeros((height, width), dtype=np.uint32)

    total_events = 0
    positive_events = 0
    negative_events = 0
    out_of_bounds = 0
    batch_count = 0
    none_count = 0

    first_ts = None
    last_ts = None
    prev_hi = None
    monotonic_bad_batches = 0

    print()
    print("[probe] START CAPTURE")
    print("[probe] Move the laser/bright spot across the camera view now.")
    print(f"[probe] duration: {args.duration_seconds:.3f}s")
    print()

    wall_start = time.time()
    deadline = wall_start + args.duration_seconds

    while time.time() < deadline:
        batch = capture.getNextEventBatch()

        if batch is None:
            none_count += 1
            time.sleep(0.001)
            continue

        try:
            n = len(batch)
        except Exception:
            n = 0

        if n == 0:
            continue

        batch_count += 1
        total_events += n

        try:
            lo = int(batch.getLowestTime())
            hi = int(batch.getHighestTime())
            if first_ts is None:
                first_ts = lo
            if prev_hi is not None and lo < prev_hi:
                monotonic_bad_batches += 1
            prev_hi = hi
            last_ts = hi
        except Exception:
            pass

        for ev in batch:
            try:
                polarity = bool(event_value(ev, "polarity"))
            except Exception:
                continue

            if not polarity:
                negative_events += 1
                continue

            positive_events += 1

            try:
                x = int(event_value(ev, "x"))
                y = int(event_value(ev, "y"))
            except Exception:
                continue

            if 0 <= x < width and 0 <= y < height:
                accum_on[y, x] += 1
            else:
                out_of_bounds += 1

    elapsed = time.time() - wall_start

    log_png = args.output_dir / f"{basename}_on_log.png"
    npy_path = args.output_dir / f"{basename}_on_counts.npy"
    json_path = args.output_dir / f"{basename}_stats.json"

    image_log = normalize_to_u8(
        accum_on,
        log_scale=True,
        percentile=args.percentile,
    )
    write_png_gray8(log_png, image_log)

    np.save(npy_path, accum_on)

    linear_png = None
    if args.linear_scale:
        linear_png = args.output_dir / f"{basename}_on_linear.png"
        image_linear = normalize_to_u8(
            accum_on,
            log_scale=False,
            percentile=args.percentile,
        )
        write_png_gray8(linear_png, image_linear)

    stats = {
        "duration_seconds_requested": args.duration_seconds,
        "duration_seconds_elapsed": elapsed,
        "resolution": [width, height],
        "threshold": args.threshold,
        "total_events": int(total_events),
        "positive_events": int(positive_events),
        "negative_events": int(negative_events),
        "positive_fraction": float(positive_events / total_events) if total_events else None,
        "mean_total_event_rate_eps": float(total_events / elapsed) if elapsed > 0 else None,
        "mean_positive_event_rate_eps": float(positive_events / elapsed) if elapsed > 0 else None,
        "batch_count": int(batch_count),
        "none_count": int(none_count),
        "out_of_bounds_positive_events": int(out_of_bounds),
        "nonzero_pixels": int(np.count_nonzero(accum_on)),
        "max_pixel_count": int(accum_on.max()) if accum_on.size else 0,
        "sum_accumulated_positive_events": int(accum_on.sum()),
        "first_camera_ts_us": int(first_ts) if first_ts is not None else None,
        "last_camera_ts_us": int(last_ts) if last_ts is not None else None,
        "camera_ts_span_s": float((last_ts - first_ts) / 1e6)
        if first_ts is not None and last_ts is not None
        else None,
        "monotonic_bad_batches": int(monotonic_bad_batches),
        "output_log_png": str(log_png),
        "output_counts_npy": str(npy_path),
        "output_linear_png": str(linear_png) if linear_png else None,
    }

    json_path.write_text(json.dumps(stats, indent=2))

    print()
    print("[probe] DONE")
    print(json.dumps(stats, indent=2))
    print()
    print(f"[probe] wrote: {log_png}")
    print(f"[probe] wrote: {npy_path}")
    print(f"[probe] wrote: {json_path}")
    if linear_png:
        print(f"[probe] wrote: {linear_png}")

    try:
        del capture
    except Exception:
        pass
    gc.collect()

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
