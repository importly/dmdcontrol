#!/usr/bin/env python3
"""
Official-style DVXplorer accumulator same-handle probe.

This intentionally follows the dv-processing accumulator sample structure:
open the camera, feed event batches through dv.EventStreamSlicer, call
dv.Accumulator.accept() on slices, then save generated frames as PNG files.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
import time
import zlib
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


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
        description="Open a DVXplorer once and run official-style accumulator windows."
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
        help="Output directory name. Default uses official_accumulator_<timestamp>.",
    )
    parser.add_argument("--windows", type=positive_int, default=5)
    parser.add_argument("--duration-seconds", type=positive_float, default=2.0)
    parser.add_argument("--gap-seconds", type=nonnegative_float, default=1.0)
    parser.add_argument(
        "--slice-ms",
        type=positive_float,
        default=33.0,
        help="EventStreamSlicer interval in milliseconds; official sample uses 33.",
    )
    parser.add_argument(
        "--camera-open-method",
        choices=["open", "dvxplorer"],
        default="open",
        help="Use dv.io.camera.open() or dv.io.camera.DVXplorer().",
    )
    parser.add_argument(
        "--set-dvxplorer-defaults",
        action="store_true",
        default=False,
        help="Set threshold 9/9, VARIABLE_5000, global hold true, and global reset false when available.",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=9,
        help="Threshold used with --set-dvxplorer-defaults.",
    )
    parser.add_argument("--event-contribution", type=float, default=0.25)
    parser.add_argument("--neutral-potential", type=float, default=0.5)
    parser.add_argument("--min-potential", type=float, default=0.0)
    parser.add_argument("--max-potential", type=float, default=1.0)
    parser.add_argument(
        "--decay-function",
        choices=["EXPONENTIAL", "LINEAR", "STEP", "NONE"],
        default="LINEAR",
        help="Accumulator decay function; official sample uses LINEAR.",
    )
    parser.add_argument(
        "--decay-param",
        type=float,
        default=1e-6,
        help="Accumulator decay parameter; official sample uses 1e-6.",
    )
    parser.add_argument(
        "--synchronous-decay",
        action="store_true",
        default=False,
        help="Enable synchronous decay. Official sample leaves this false.",
    )
    parser.add_argument(
        "--ignore-polarity",
        action="store_true",
        default=False,
        help="Make all events contribute in the same direction.",
    )
    parser.add_argument(
        "--save-initial-frames",
        type=positive_int,
        default=5,
        help="Save the first N slicer-generated frames per window.",
    )
    parser.add_argument(
        "--save-every-n-frames",
        type=positive_int,
        default=10,
        help="After initial frames, save every Nth generated frame.",
    )
    return parser


def _monotonic_seconds() -> float:
    return time.time()


def _batch_time_range_us(batch):
    try:
        return int(batch.getLowestTime()), int(batch.getHighestTime())
    except Exception:
        return None


def _camera_running(camera) -> bool:
    method = getattr(camera, "isRunning", None)
    return bool(method()) if callable(method) else True


def _call_if_available(obj, name: str, *args):
    method = getattr(obj, name, None)
    if not callable(method):
        print(f"[official_accu] {name} unavailable")
        return None
    result = method(*args)
    print(f"[official_accu] {name}{args} -> OK")
    return result


def _open_camera(dv, method: str):
    if method == "open":
        print("[official_accu] opening with dv.io.camera.open()")
        return dv.io.camera.open()
    constructor = getattr(dv.io.camera, "DVXplorer", None)
    if not callable(constructor):
        raise SystemExit("dv.io.camera.DVXplorer is not available in this environment")
    print("[official_accu] opening with dv.io.camera.DVXplorer()")
    return constructor()


def _set_dvxplorer_defaults(dv, camera, threshold: int) -> None:
    _call_if_available(camera, "setContrastThresholdOn", threshold)
    _call_if_available(camera, "setContrastThresholdOff", threshold)
    dvxplorer = getattr(dv.io.camera, "DVXplorer", None)
    readout_enum = getattr(dvxplorer, "ReadoutFPS", None)
    if readout_enum is not None and hasattr(readout_enum, "VARIABLE_5000"):
        _call_if_available(camera, "setReadoutFPS", readout_enum.VARIABLE_5000)
    _call_if_available(camera, "setGlobalHold", True)
    _call_if_available(camera, "setGlobalReset", False)


def _configure_accumulator(dv, camera, args):
    accumulator = dv.Accumulator(camera.getEventResolution())
    accumulator.setEventContribution(args.event_contribution)
    accumulator.setNeutralPotential(args.neutral_potential)
    accumulator.setMinPotential(args.min_potential)
    accumulator.setMaxPotential(args.max_potential)
    accumulator.setDecayFunction(getattr(dv.Accumulator.Decay, args.decay_function))
    accumulator.setDecayParam(args.decay_param)
    accumulator.setSynchronousDecay(args.synchronous_decay)
    accumulator.setIgnorePolarity(args.ignore_polarity)
    return accumulator


def _to_u8_image(image) -> np.ndarray:
    array = np.asarray(image)
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)

    array = array.astype(np.float32)
    if array.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    minimum = float(np.min(array))
    maximum = float(np.max(array))
    if math.isfinite(minimum) and math.isfinite(maximum) and minimum >= 0.0 and maximum <= 1.0:
        return np.ascontiguousarray(np.clip(array * 255.0, 0, 255).astype(np.uint8))
    if maximum <= minimum:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = (array - minimum) * (255.0 / (maximum - minimum))
    return np.ascontiguousarray(np.clip(scaled, 0, 255).astype(np.uint8))


def _write_png(path: Path, image) -> None:
    image_u8 = _to_u8_image(image)
    if image_u8.ndim == 2:
        color_type = 0
        rows = [b"\x00" + image_u8[row].tobytes() for row in range(image_u8.shape[0])]
    elif image_u8.ndim == 3 and image_u8.shape[2] in (3, 4):
        color_type = 2 if image_u8.shape[2] == 3 else 6
        rows = [b"\x00" + image_u8[row].tobytes() for row in range(image_u8.shape[0])]
    else:
        raise ValueError(f"unsupported image shape for PNG: {image_u8.shape}")

    height, width = image_u8.shape[:2]
    payload = b"\x89PNG\r\n\x1a\n"
    payload += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
    payload += _png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
    payload += _png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def _png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def capture_official_window(dv, camera, label: str, out_dir: Path, args) -> dict:
    accumulator = _configure_accumulator(dv, camera, args)
    slicer = dv.EventStreamSlicer()

    frame_count = 0
    saved_pngs = []
    last_image = None

    def accumulate_events(event_slice):
        nonlocal frame_count, last_image
        accumulator.accept(event_slice)
        frame = accumulator.generateFrame()
        last_image = np.array(frame.image, copy=True)
        frame_count += 1
        if frame_count <= args.save_initial_frames or frame_count % args.save_every_n_frames == 0:
            png_path = out_dir / f"{label}_frame_{frame_count:04d}.png"
            _write_png(png_path, last_image)
            saved_pngs.append(str(png_path))

    slicer.doEveryTimeInterval(timedelta(milliseconds=args.slice_ms), accumulate_events)

    total_events = 0
    batch_count = 0
    none_count = 0
    first_ts = None
    last_ts = None

    print(f"\n=== {label} ===")
    print("Move laser/flashlight/diffuse spot during this official accumulator window.")

    deadline = _monotonic_seconds() + args.duration_seconds
    while _monotonic_seconds() < deadline and _camera_running(camera):
        events = camera.getNextEventBatch()
        if events is None:
            none_count += 1
            time.sleep(0.001)
            continue

        batch_count += 1
        try:
            total_events += len(events)
        except TypeError:
            pass

        time_range = _batch_time_range_us(events)
        if time_range is not None:
            lo, hi = time_range
            first_ts = lo if first_ts is None else min(first_ts, lo)
            last_ts = hi if last_ts is None else max(last_ts, hi)

        slicer.accept(events)

    if last_image is None:
        last_image = np.array(accumulator.generateFrame().image, copy=True)

    final_png = out_dir / f"{label}_final.png"
    _write_png(final_png, last_image)
    if str(final_png) not in saved_pngs:
        saved_pngs.append(str(final_png))

    stats = {
        "label": label,
        "seconds": args.duration_seconds,
        "events": int(total_events),
        "batches": int(batch_count),
        "none_count": int(none_count),
        "frame_count": int(frame_count),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "final_png": str(final_png),
        "saved_pngs": saved_pngs,
    }
    print(json.dumps(stats, indent=2))
    return stats


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    import dv_processing as dv

    output_name = args.name or f"official_accumulator_{time.strftime('%Y%m%d-%H%M%S')}"
    out_dir = args.output_root / output_name
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[official_accu] dv_processing version:", getattr(dv, "__version__", "unknown"))
    print("[official_accu] dv_processing file:", getattr(dv, "__file__", None))

    camera = _open_camera(dv, args.camera_open_method)
    camera_opens = 1
    try:
        print("[official_accu] capture type:", type(camera))
        print(
            "[official_accu] camera name:",
            camera.getCameraName() if hasattr(camera, "getCameraName") else "unknown",
        )
        print("[official_accu] isRunning:", _camera_running(camera))
        print(
            "[official_accu] event stream:",
            camera.isEventStreamAvailable() if hasattr(camera, "isEventStreamAvailable") else "unknown",
        )

        if hasattr(camera, "isEventStreamAvailable") and not camera.isEventStreamAvailable():
            raise RuntimeError("Input camera does not provide an event stream.")

        print("[official_accu] resolution:", tuple(camera.getEventResolution()))
        if args.set_dvxplorer_defaults:
            _set_dvxplorer_defaults(dv, camera, args.threshold)

        windows = []
        for index in range(1, args.windows + 1):
            label = f"window_{index:02d}_official_accumulator"
            windows.append(capture_official_window(dv, camera, label, out_dir, args))
            if index < args.windows and args.gap_seconds > 0:
                time.sleep(args.gap_seconds)

        stats = {
            "summary": {
                "camera_opens": camera_opens,
                "output_dir": str(out_dir),
                "camera_open_method": args.camera_open_method,
                "set_dvxplorer_defaults": args.set_dvxplorer_defaults,
                "threshold": args.threshold,
                "windows": args.windows,
                "duration_seconds": args.duration_seconds,
                "gap_seconds": args.gap_seconds,
                "slice_ms": args.slice_ms,
                "event_contribution": args.event_contribution,
                "neutral_potential": args.neutral_potential,
                "min_potential": args.min_potential,
                "max_potential": args.max_potential,
                "decay_function": args.decay_function,
                "decay_param": args.decay_param,
                "synchronous_decay": args.synchronous_decay,
                "ignore_polarity": args.ignore_polarity,
            },
            "windows": windows,
        }
        stats_path = out_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")

        print("\n[official_accu] OUT:", out_dir)
        print("[official_accu] stats:", stats_path)
        return 0
    finally:
        pass
        # try:
        #     del camera
        # except Exception:
        #     pass


if __name__ == "__main__":
    raise SystemExit(run())
