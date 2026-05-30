"""Pure DMD preview rendering helpers for offline and live web previews."""

from __future__ import annotations

import io
import json
import threading
import time
from urllib import request

import numpy as np
from PIL import Image

from dmdcontrol.patterns.calibration_square import build_calibration_square_frame
from dmdcontrol.patterns.kernel import build_kernel_frames
from dmdcontrol.patterns.modes import (
    NUMBER_SEQUENCE,
    PATTERN_NAMES,
    build_patterns,
    default_calibration_square_state,
    generate_number_rgb,
)
from dmdcontrol.patterns.paired import (
    CALIBRATION_DOT_PAIR_TEST,
    DMD_HEIGHT,
    DMD_WIDTH,
    DynamicGradientPairFrameProvider,
    DynamicSnakePairFrameProvider,
    KERNEL_STATIC_PAIR_TEST,
    PAIR_TESTS,
    STATIC_PAIR_TESTS,
    compose_pair_frame,
    generate_dot_frame,
    generate_static_frame,
)
from dmdcontrol.support.constants import BITPLANES

BITPLANE_LABELS = tuple(
    [f"G{i}" for i in range(8)]
    + [f"R{i}" for i in range(8)]
    + [f"B{i}" for i in range(8)]
)
# GRB
_BITPLANE_CHANNELS = (1,) * 8 + (0,) * 8 + (2,) * 8
_BITPLANE_BITS = tuple(range(8)) * 3


def _json_safe_value(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return value


def _bitplane_label(plane_index):
    if 0 <= plane_index < len(BITPLANE_LABELS):
        return BITPLANE_LABELS[plane_index]
    return f"P{plane_index}"


def build_lut_preview_metadata(entries, timing=None):
    """Describe a DLPC900 video-pattern LUT in preview-friendly JSON data."""

    preview_entries = []
    cursor_us = 0
    for index, entry in enumerate(entries):
        plane_index = int(entry[0])
        exposure_us = int(entry[1])
        clear = bool(entry[2])
        bit_depth = int(entry[3]) if len(entry) > 3 else 1
        led_select = int(entry[4]) if len(entry) > 4 else None
        dark_us = int(entry[5]) if len(entry) > 5 else 0
        trig2_disabled = bool(entry[6]) if len(entry) > 6 else False
        image_index = int(entry[7]) if len(entry) > 7 else plane_index
        label = _bitplane_label(plane_index)
        preview_entries.append(
            {
                "index": int(index),
                "plane_index": plane_index,
                "plane_label": label,
                "channel": label[0],
                "bit": int(label[1:]) if label[1:].isdigit() else plane_index,
                "exposure_us": exposure_us,
                "dark_us": dark_us,
                "start_us": int(cursor_us),
                "end_us": int(cursor_us + exposure_us),
                "segment_end_us": int(cursor_us + exposure_us + dark_us),
                "clear": clear,
                "bit_depth": bit_depth,
                "led_select": led_select,
                "trig2_disabled": trig2_disabled,
                "image_index": image_index,
            }
        )
        cursor_us += exposure_us + dark_us

    return {
        "bitplane_order": list(BITPLANE_LABELS),
        "entries": preview_entries,
        "timing": _json_safe_value(dict(timing or {})),
    }


class PreviewEngine:
    """Small no-GL engine implementing PatternEngine's pure packing API."""

    def __init__(self, width=DMD_WIDTH, height=DMD_HEIGHT):
        self.width = width
        self.height = height

    def pack_patterns(self, binary_images):
        if len(binary_images) != BITPLANES:
            raise ValueError(f"expected {BITPLANES} binary images, got {len(binary_images)}")
        r = np.zeros((self.height, self.width), dtype=np.uint8)
        g = np.zeros((self.height, self.width), dtype=np.uint8)
        b = np.zeros((self.height, self.width), dtype=np.uint8)
        for i in range(8):
            g |= np.asarray(binary_images[i], dtype=np.uint8) << i
            r |= np.asarray(binary_images[i + 8], dtype=np.uint8) << i
            b |= np.asarray(binary_images[i + 16], dtype=np.uint8) << i
        return np.ascontiguousarray(np.stack([r, g, b], axis=-1))

    def rgb_to_binary_patterns(self, rgb_array):
        if rgb_array.shape[:2] != (self.height, self.width):
            raise ValueError(
                f"RGB array must be {self.height}x{self.width}, got {rgb_array.shape[:2]}"
            )
        patterns = []
        for bit in range(8):
            patterns.append(((rgb_array[:, :, 1] >> bit) & 1).astype(np.uint8))
        for bit in range(8):
            patterns.append(((rgb_array[:, :, 0] >> bit) & 1).astype(np.uint8))
        for bit in range(8):
            patterns.append(((rgb_array[:, :, 2] >> bit) & 1).astype(np.uint8))
        return patterns

    def generate_checkerboard(self, block_size=32):
        y, x = np.indices((self.height, self.width))
        checker = ((x // block_size) + (y // block_size)) % 2
        checker = checker.astype(np.uint8)
        return [checker for _ in range(BITPLANES)]

    def generate_lines(self):
        x = np.indices((self.height, self.width))[1]
        lines = (x % 2).astype(np.uint8)
        return [lines for _ in range(BITPLANES)]

    def generate_solid(self, val):
        solid = np.full((self.height, self.width), val, dtype=np.uint8)
        return [solid for _ in range(BITPLANES)]

    def generate_gradient(self):
        patterns = []
        x = np.indices((self.height, self.width))[1]
        for i in range(BITPLANES):
            bit_index = i % 8
            threshold = (self.width / 8) * bit_index
            patterns.append((x >= threshold).astype(np.uint8))
        return patterns

    def generate_ordering_diagnostic_patterns(self, sub_width=512, sub_height=512):
        patterns = []
        sub_width = min(sub_width, self.width)
        sub_height = min(sub_height, self.height)
        y_start = max(0, (self.height - sub_height) // 2)
        x_start = max(0, (self.width - sub_width) // 2)
        block_w = max(1, sub_width // BITPLANES)
        for i in range(BITPLANES):
            img = np.zeros((self.height, self.width), dtype=np.uint8)
            bx_start = x_start + (i * block_w)
            bx_end = min(x_start + sub_width, bx_start + block_w)
            img[y_start: y_start + sub_height, bx_start:bx_end] = 1
            patterns.append(img)
        return patterns

    def generate_snake_frame(self, frame_index=0, grid_w=24, grid_h=13):
        grid = np.zeros((grid_h, grid_w), dtype=np.uint8)
        path_len = grid_w * grid_h
        head = frame_index % path_len
        for segment in range(6):
            pos = (head - segment) % path_len
            row = pos // grid_w
            col = pos % grid_w
            grid[row, col] = max(64, 255 - segment * 32)
        block_w = max(1, self.width // grid_w)
        block_h = max(1, self.height // grid_h)
        frame_2d = np.repeat(np.repeat(grid, block_h, axis=0), block_w, axis=1)
        padded = np.zeros((self.height, self.width), dtype=np.uint8)
        h, w = frame_2d.shape
        padded[: min(h, self.height), : min(w, self.width)] = frame_2d[
            : min(h, self.height), : min(w, self.width)
        ]
        return np.ascontiguousarray(np.stack([padded, padded, padded], axis=-1))


def _solid_rgb(channel, width=DMD_WIDTH, height=DMD_HEIGHT):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :, channel] = 255
    return np.ascontiguousarray(frame)


def _clock_preview_frame(frame_index, width=DMD_WIDTH, height=DMD_HEIGHT):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    stripe = max(1, width // 16)
    x0 = (frame_index % 16) * stripe
    frame[:, x0: min(width, x0 + stripe), :] = 255
    return np.ascontiguousarray(frame)


def _kernel_preview_frame(engine, frame_index):
    frames, _metadata = build_kernel_frames(
        engine,
        kernel_px=30,
        slots_per_frame=BITPLANES,
        leader_frames=0,
        blank_end_frame=False,
    )
    return frames[frame_index % len(frames)]


def render_single_frame(test="coarse-grid", frame_index=0, width=DMD_WIDTH, height=DMD_HEIGHT):
    if test not in PATTERN_NAMES:
        raise ValueError(f"unsupported single-DMD test: {test}")
    engine = PreviewEngine(width=width, height=height)

    if test == "colors":
        return _solid_rgb(frame_index % 3, width=width, height=height)
    if test == "numbers":
        number = NUMBER_SEQUENCE[frame_index % len(NUMBER_SEQUENCE)]
        return generate_number_rgb(number, width=width, height=height)
    if test == "calibr-square":
        state = default_calibration_square_state(width, height)
        return build_calibration_square_frame(engine, state)
    if test == "snake":
        return engine.generate_snake_frame(frame_index=frame_index)
    if test == "clock":
        return _clock_preview_frame(frame_index, width=width, height=height)
    if test == "kernel":
        return _kernel_preview_frame(engine, frame_index)

    _label, patterns, dynamic_kind = build_patterns(engine, test)
    if patterns is None or dynamic_kind is not None:
        raise ValueError(f"unsupported preview mode: {test}")
    return engine.pack_patterns(patterns)


def render_pair_frame(test="coarse-grid", test_a=None, test_b=None, frame_index=0):
    if test not in PAIR_TESTS:
        raise ValueError(f"unsupported paired test: {test}")

    if test in STATIC_PAIR_TESTS:
        frame_a = generate_static_frame(test_a or test, route_label="A")
        frame_b = generate_static_frame(test_b or test, route_label="B")
        return compose_pair_frame(frame_a, frame_b)

    if test == "gradient":
        frame_a, frame_b = DynamicGradientPairFrameProvider()._frame_for_index(frame_index)
        return compose_pair_frame(frame_a, frame_b)
    if test == "snake":
        frame_a, frame_b = DynamicSnakePairFrameProvider()._frame_for_index(frame_index)
        return compose_pair_frame(frame_a, frame_b)
    if test == CALIBRATION_DOT_PAIR_TEST:
        engine = PreviewEngine()
        state = default_calibration_square_state(DMD_WIDTH, DMD_HEIGHT)
        frame_a = build_calibration_square_frame(engine, state)
        frame_b = generate_dot_frame()
        return compose_pair_frame(frame_a, frame_b)
    if test == KERNEL_STATIC_PAIR_TEST:
        engine = PreviewEngine()
        frame_a = _kernel_preview_frame(engine, frame_index)
        frame_b = generate_static_frame(test_b or "checkerboard", route_label="B")
        return compose_pair_frame(frame_a, frame_b)

    raise ValueError(f"unsupported paired test: {test}")


def render_offline_frame(
        layout="pair",
        test="coarse-grid",
        test_a=None,
        test_b=None,
        frame_index=0,
):
    if layout == "pair":
        return render_pair_frame(test=test, test_a=test_a, test_b=test_b, frame_index=frame_index)
    if layout == "single":
        return render_single_frame(test=test, frame_index=frame_index)
    raise ValueError("layout must be 'pair' or 'single'")


def extract_bitplane(packed_frame, plane):
    if plane < 0 or plane >= BITPLANES:
        raise ValueError(f"plane must be in [0, {BITPLANES - 1}]")
    channel = _BITPLANE_CHANNELS[plane]
    bit = _BITPLANE_BITS[plane]
    return (((packed_frame[:, :, channel] >> bit) & 1) * 255).astype(np.uint8)


def render_bitplane_image(packed_frame, plane):
    return np.ascontiguousarray(extract_bitplane(packed_frame, plane))


def render_view_image(packed_frame, view="packed", plane=0):
    if view == "packed":
        return packed_frame
    if view == "bitplane":
        return render_bitplane_image(packed_frame, plane)
    raise ValueError("view must be 'packed' or 'bitplane'")


def render_png_bytes(image_array):
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(image_array)).save(buf, format="PNG")
    return buf.getvalue()


def render_preview_png(
        layout="pair",
        test="coarse-grid",
        test_a=None,
        test_b=None,
        frame_index=0,
        view="packed",
        plane=0,
):
    packed = render_offline_frame(
        layout=layout,
        test=test,
        test_a=test_a,
        test_b=test_b,
        frame_index=frame_index,
    )
    return render_png_bytes(render_view_image(packed, view=view, plane=plane))


class LiveFrameStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._frame = None
        self._metadata = {}
        self._updated_at = None

    def set_png(self, png_bytes, metadata=None):
        image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        frame = np.ascontiguousarray(np.array(image, dtype=np.uint8))
        with self._lock:
            self._frame = frame
            self._metadata = dict(metadata or {})
            self._updated_at = time.time()

    def get_frame(self):
        with self._lock:
            if self._frame is None:
                return None, {}, None
            return self._frame.copy(), dict(self._metadata), self._updated_at

    def get_metadata(self):
        with self._lock:
            return dict(self._metadata), self._updated_at

    def has_frame(self):
        with self._lock:
            return self._frame is not None


class LivePreviewPoster:
    def __init__(self, url, fps=1.0):
        if fps <= 0:
            raise ValueError("fps must be positive")
        self.url = url
        self.interval_s = 1.0 / float(fps)
        self._last_post_s = 0.0
        self._active_thread = None
        self._lock = threading.Lock()

    def maybe_post_pair(self, frame_a, frame_b, metadata=None, force=False):
        post_metadata = {"layout": "pair"}
        post_metadata.update(dict(metadata or {}))
        self.maybe_post(compose_pair_frame(frame_a, frame_b), post_metadata, force=force)

    def maybe_post(self, packed_frame, metadata=None, force=False):
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_post_s < self.interval_s:
                return
            if self._active_thread is not None and self._active_thread.is_alive():
                return
            self._last_post_s = now
            frame_copy = np.ascontiguousarray(packed_frame.copy())
            metadata_copy = dict(metadata or {})
            self._active_thread = threading.Thread(
                target=self._post_frame,
                args=(frame_copy, metadata_copy),
                daemon=True,
            )
            self._active_thread.start()

    def _post_frame(self, packed_frame, metadata):
        body = render_png_bytes(packed_frame)
        headers = {
            "Content-Type": "image/png",
            "X-DMD-Metadata": json.dumps(metadata, sort_keys=True),
        }
        req = request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            request.urlopen(req, timeout=1.0).close()
        except Exception:
            pass

    def close(self, timeout=1.0):
        with self._lock:
            thread = self._active_thread
        if thread is not None:
            thread.join(timeout=timeout)
