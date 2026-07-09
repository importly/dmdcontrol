from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image


def _write_accumulation_image_artifacts(
    run_directory,
    accumulated,
    *,
    include_filtered,
    contact_sheet_columns=None,):
    frame_artifacts = []
    filtered_frame_artifacts = []
    scale_max = _grayscale_scale_max(accumulated)
    for index, frame in enumerate(accumulated, start=1):
        frame_path = run_directory.path / f"accumulated_{index:03d}.png"
        _write_grayscale_png(frame_path, frame, scale_max=scale_max)
        frame_artifacts.append(frame_path.name)
        if include_filtered:
            filtered_frame_path = (run_directory.path / f"filtered_accumulated_{index:03d}.png")
            _write_grayscale_png(filtered_frame_path, frame, scale_max=scale_max)
            filtered_frame_artifacts.append(filtered_frame_path.name)

    contact_sheet = _contact_sheet(
        accumulated,
        scale_max=scale_max,
        cols=contact_sheet_columns,
    )
    _write_grayscale_png(run_directory.contact_sheet_path, contact_sheet, scale_max=255)

    filtered_contact_sheet_artifact = None
    if include_filtered:
        filtered_contact_sheet_artifact = "filtered_contact_sheet.png"
        _write_grayscale_png(
            run_directory.path / filtered_contact_sheet_artifact,
            contact_sheet,
            scale_max=255,
        )

    return {
        "frame_artifacts": frame_artifacts,
        "filtered_frame_artifacts": filtered_frame_artifacts,
        "filtered_contact_sheet_artifact": filtered_contact_sheet_artifact,
    }

def _contact_sheet(frames, *, scale_max=None, cols=None):
    if len(frames) == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    normalized = [_normalize_grayscale(frame, scale_max=scale_max) for frame in frames]
    frame_h, frame_w = normalized[0].shape
    cols = (
        max(1,
            int(cols)) if cols is not None else max(1,
                                                    math.ceil(math.sqrt(len(normalized)))))
    rows = math.ceil(len(normalized) / cols)
    sheet = np.zeros((rows * frame_h, cols * frame_w), dtype=np.uint8)
    for index, frame in enumerate(normalized):
        row = index // cols
        col = index % cols
        y0 = row * frame_h
        x0 = col * frame_w
        sheet[y0:y0 + frame_h, x0:x0 + frame_w] = frame
    return sheet

def _grayscale_scale_max(frames):
    array = np.asarray(frames, dtype=np.float32)
    if array.size == 0:
        return 0.0
    return float(np.max(np.abs(array)))

def _normalize_grayscale(frame, *, scale_max=None):
    array = np.asarray(frame, dtype=np.float32)
    if array.ndim != 2:
        raise ValueError("frame must be a 2D array")
    if array.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)
    magnitude = np.abs(array)
    maximum = float(scale_max) if scale_max is not None else float(np.max(magnitude))
    if maximum <= 0:
        return np.zeros(array.shape, dtype=np.uint8)
    scaled = np.log1p(magnitude) * (255.0 / np.log1p(maximum))
    return np.rint(np.clip(scaled, 0, 255)).astype(np.uint8)

def _write_grayscale_png(path, frame, *, scale_max=None):
    image = _normalize_grayscale(frame, scale_max=scale_max)
    Image.fromarray(np.ascontiguousarray(image)).save(Path(path), format="PNG")
