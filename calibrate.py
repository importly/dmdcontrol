"""Measure where the 16x16 output grid lands on the camera (Run.Kernel.grid_centre / grid_px).

fit_grid matches each output pixel's area mean to the digital same convolution (conv16) over
many samples, so the grid sits where the signal really lands. collect.py fits after batch 0 of
every kernel run and warns with new config values if the grid moved; to fit a finished run:

    uv run python calibrate.py runs/<output_root>/<run>

The grid and the 16x16 output made from it are in dmdcontrol/runtime/output_grid.py.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from dmdcontrol.runtime.output_grid import SIDE, Grid, Roi, sample_grid

FIT_SUBSAMPLES = 6     # points per output pixel side, averaged: close to each output pixel's area mean
MAX_EDGE_SHIFT = 0.25  # output pixels: how far the grid's edge may move before the config should change


@dataclass(frozen=True)
class GridFit:
    grid: Grid
    r: float  # mean over samples of corr(output pixel means, conv16)


def _mean_corr(a: torch.Tensor, b: torch.Tensor) -> float:
    a = a.flatten(1) - a.flatten(1).mean(1, keepdim=True)
    b = b.flatten(1) - b.flatten(1).mean(1, keepdim=True)
    return float(((a * b).sum(1) / (a.norm(dim=1) * b.norm(dim=1)).clamp_min(1e-12)).mean())


def fit_grid(frames: np.ndarray, conv: np.ndarray, start: Grid, roi: Roi) -> GridFit:
    """Fit the grid of conv (N, 16, 16) onto frames (N, ROI height, ROI width), starting from start."""
    out_t = torch.from_numpy(np.asarray(frames, dtype=np.float32))
    conv_t = torch.from_numpy(np.asarray(conv, dtype=np.float32))
    cx, cy = start.in_roi(roi)
    params = [cx, cy, start.px, start.py]
    steps = [start.px / 3, start.py / 3, start.px * 0.04, start.py * 0.04]

    def score(p: list[float]) -> float:
        samples = sample_grid(out_t, p[0], p[1], p[2], p[3], FIT_SUBSAMPLES)
        return _mean_corr(F.avg_pool2d(samples[:, None], FIT_SUBSAMPLES)[:, 0], conv_t)

    best = score(params)
    for _ in range(7):  # coordinate ascent, halving the steps each round
        for i in range(4):
            while True:
                candidates = [params[:i] + [params[i] + d * steps[i]] + params[i + 1:] for d in (-1, 1)]
                value, candidate = max((score(c), c) for c in candidates)
                if value <= best + 1e-6:
                    break
                best, params = value, candidate
        steps = [s / 2 for s in steps]
    return GridFit(Grid(params[0] + roi[0], params[1] + roi[1], params[2], params[3]), best)


def grid_report(fit: GridFit, configured: Grid, roi: Roi) -> tuple[str, str | None]:
    """A line describing the fit, and a warning with the config to use if the grid moved or left the ROI."""
    g = fit.grid
    # how far the fitted grid's edges sit from the configured one's, centre offset and size together
    edge_x = abs(g.cx - configured.cx) + abs(g.px - configured.px) * SIDE / 2
    edge_y = abs(g.cy - configured.cy) + abs(g.py - configured.py) * SIDE / 2
    line = (f'grid centre ({g.cx:.1f}, {g.cy:.1f}) on the sensor, {g.px:.2f} x {g.py:.2f} camera px per output '
            f'px (configured ({configured.cx:.1f}, {configured.cy:.1f}), {configured.px:.2f} x {configured.py:.2f}); '
            f'edges moved up to {edge_x:.1f}, {edge_y:.1f} px; r {fit.r:.3f}')
    moved = max(edge_x / configured.px, edge_y / configured.py) > MAX_EDGE_SHIFT
    if not moved and g.inside(roi):
        return line, None
    sx, sy, w, h = g.roi()
    return line, (f'Output grid {"moved" if moved else "is not inside Camera.ROI"}: set Run.Kernel '
                  f'grid_centre: [{g.cx:.1f}, {g.cy:.1f}], grid_px: [{g.px:.2f}, {g.py:.2f}] and Camera.ROI '
                  f'start_x {sx}, start_y {sy}, width {w}, height {h}')


def main(run_dir: Path, rows: int = 220) -> None:
    import h5py

    from dmdcontrol.runtime.dmd_conv import combine

    with h5py.File(run_dir / 'data.h5', 'r') as data_file:
        frames, conv16 = data_file['frames'], data_file['conv16']
        assert isinstance(frames, h5py.Dataset) and isinstance(conv16, h5py.Dataset)
        n = min(rows, frames.shape[0])
        terms = np.asarray(frames[:n]).transpose(1, 0, 2, 3)
        conv = np.asarray(conv16[:n])
        attrs = data_file.attrs
        gamma = float(np.asarray(attrs['gamma']))
        start_x, start_y, width, height = (int(v) for v in np.asarray(attrs['roi']))
        centre, size = np.asarray(attrs['grid_centre'], dtype=float), np.asarray(attrs['grid_px'], dtype=float)
    roi = (start_x, start_y, width, height)
    configured = Grid(centre[0], centre[1], size[0], size[1])
    fit = fit_grid(combine(terms, gamma), conv, configured, roi)
    line, warning = grid_report(fit, configured, roi)
    print(f'{run_dir.name}, {n} samples: {line}')
    print(warning or 'The configured grid and ROI are right.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
