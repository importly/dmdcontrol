import argparse
import os
import struct
import time
import zlib
from pathlib import Path


def _maybe_call(value):
    return value() if callable(value) else value


def _pair_from_coordinate(coordinate):
    if isinstance(coordinate, dict):
        return int(coordinate["x"]), int(coordinate["y"])
    if hasattr(coordinate, "x") and hasattr(coordinate, "y"):
        return int(_maybe_call(coordinate.x)), int(_maybe_call(coordinate.y))
    return int(coordinate[0]), int(coordinate[1])


def _event_xy_pairs(events):
    if hasattr(events, "coordinates"):
        for coordinate in events.coordinates():
            yield _pair_from_coordinate(coordinate)
        return

    if hasattr(events, "numpy"):
        array = events.numpy()
        names = getattr(getattr(array, "dtype", None), "names", None) or ()
        if "x" in names and "y" in names:
            for row in array:
                yield int(row["x"]), int(row["y"])
            return
        for row in array:
            yield _pair_from_coordinate(row)
        return

    for event in events:
        yield _pair_from_coordinate(event)


def _normalize_resolution(resolution):
    if resolution is None:
        return None
    if isinstance(resolution, (tuple, list)) and len(resolution) >= 2:
        width, height = int(resolution[0]), int(resolution[1])
    elif hasattr(resolution, "width") and hasattr(resolution, "height"):
        width = int(_maybe_call(resolution.width))
        height = int(_maybe_call(resolution.height))
    else:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _read_resolution(source):
    for method_name in ("getEventResolution", "getResolution"):
        method = getattr(source, method_name, None)
        if method is None:
            continue
        try:
            resolution = _normalize_resolution(method())
        except TypeError:
            continue
        if resolution is not None:
            return resolution
    return None


def accumulate_batches(batches, resolution=None):
    resolution = _normalize_resolution(resolution)
    total_events = 0
    batch_count = 0

    if resolution is not None:
        width, height = resolution
        pixels = [0] * (width * height)
        for batch in batches:
            batch_count += 1
            for x, y in _event_xy_pairs(batch):
                total_events += 1
                if 0 <= x < width and 0 <= y < height:
                    pixels[(y * width) + x] += 1
        return pixels, total_events, batch_count, width, height

    coordinates = []
    max_x = -1
    max_y = -1
    for batch in batches:
        batch_count += 1
        for x, y in _event_xy_pairs(batch):
            total_events += 1
            if x < 0 or y < 0:
                continue
            coordinates.append((x, y))
            max_x = max(max_x, x)
            max_y = max(max_y, y)

    if max_x < 0 or max_y < 0:
        raise ValueError("No events found and no event resolution was available")

    width, height = max_x + 1, max_y + 1
    pixels = [0] * (width * height)
    for x, y in coordinates:
        pixels[(y * width) + x] += 1
    return pixels, total_events, batch_count, width, height


def _png_chunk(chunk_type, data):
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack("!I", len(data)) + chunk_type + data + struct.pack("!I", crc)


def write_grayscale_png(path, pixels, width, height):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(pixels) != width * height:
        raise ValueError("Pixel count does not match image dimensions")

    max_count = max(pixels, default=0)
    if max_count:
        image_bytes = bytes(min(255, round((value * 255) / max_count)) for value in pixels)
    else:
        image_bytes = bytes(len(pixels))

    scanlines = bytearray()
    for row in range(height):
        start = row * width
        scanlines.append(0)
        scanlines.extend(image_bytes[start:start + width])

    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(scanlines)))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def accumulate_aedat4(recording_path, fallback_resolution=None):
    import dv_processing as dv

    reader = dv.io.MonoCameraRecording(str(recording_path))
    resolution = _read_resolution(reader) or _normalize_resolution(fallback_resolution)
    batches = []
    empty_reads = 0

    while reader.isRunning():
        events = reader.getNextEventBatch()
        if events is None:
            empty_reads += 1
            if empty_reads > 50:
                break
            continue
        empty_reads = 0
        batches.append(events)

    return accumulate_batches(batches, resolution=resolution)


def run_capture(seconds, output_path=None):
    script_dir = Path(__file__).resolve().parent
    os.chdir(script_dir)

    from camera import Camera

    camera = Camera()
    fallback_resolution = _read_resolution(camera.camera)
    started = False
    try:
        camera.record()
        started = True
        time.sleep(seconds)
    finally:
        if started:
            camera.stop()

    recording_path = Path(camera.filename)
    pixels, total_events, batch_count, width, height = accumulate_aedat4(
        recording_path,
        fallback_resolution=fallback_resolution,
    )
    png_path = Path(output_path) if output_path else recording_path.with_name("accumulated_events.png")
    if not png_path.is_absolute():
        png_path = script_dir / png_path
    write_grayscale_png(png_path, pixels, width, height)

    return {
        "png_path": png_path,
        "recording_path": recording_path,
        "total_events": total_events,
        "batch_count": batch_count,
        "width": width,
        "height": height,
        "seconds": seconds,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Briefly record DAVIS events and save an accumulated PNG.")
    parser.add_argument("--seconds", type=float, default=0.5, help="Capture duration, clamped to 0.05-5.0 seconds.")
    parser.add_argument("--output", type=Path, help="Optional PNG output path.")
    args = parser.parse_args(argv)

    seconds = max(0.05, min(args.seconds, 5.0))
    summary = run_capture(seconds=seconds, output_path=args.output)

    print(f"PNG: {summary['png_path']}")
    print(
        "Summary: "
        f"{summary['total_events']} events from {summary['batch_count']} batches, "
        f"{summary['width']}x{summary['height']} image, "
        f"{summary['seconds']:.2f}s capture, "
        f"recording={summary['recording_path']}"
    )


if __name__ == "__main__":
    main()
