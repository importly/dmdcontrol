"""The 16x16 output grid on the camera, and the 16x16 output made from a capture.

A 16x16 input convolved with a 9x9 kernel, zero padded, gives a 16x16 output on the input's own
grid ('same' convolution), so binary CNN layers stack. On the camera that grid is 16x16 output
pixels centred at Run.Kernel.grid_centre, Run.Kernel.grid_px camera px each (calibrate.py
measures both). region16 makes the output: the grid resampled bilinearly onto 12x12 points per
output pixel, then downscaled to 16x16 bilinearly with antialiasing. The translator's simulator
makes its targets with the same steps (eodla_sim.region16).

Imports torch, so the runtime package does not import this module: only kernel mode needs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
import torch
import torch.nn.functional as F

from dmdcontrol.utils import CONFIG

SIDE = 16        # output grid: the same convolution of a 16x16 input
SUBSAMPLES = 12  # region16: bilinear points per output pixel side before the downscale
MARGIN = 1       # Grid.roi: output pixels of margin around the grid on each side

Roi = tuple[int, int, int, int]  # start_x, start_y, width, height on the sensor


@dataclass(frozen=True)
class Grid:
    """The output grid on the sensor: centre (sensor px, pixel centres at integers) and camera px per output pixel."""

    cx: float
    cy: float
    px: float
    py: float

    @classmethod
    def configured(cls) -> Grid:
        settings = CONFIG.Run.Kernel
        return cls(settings.grid_centre[0], settings.grid_centre[1], settings.grid_px[0], settings.grid_px[1])

    def in_roi(self, roi: Roi) -> tuple[float, float]:
        """The centre in ROI px."""
        return self.cx - roi[0], self.cy - roi[1]

    def edges(self, roi: Roi) -> tuple[float, float, float, float]:
        """The grid's outer edges in ROI px: left, right, top, bottom (pixel i spans i - 0.5 .. i + 0.5)."""
        cx, cy = self.in_roi(roi)
        return cx - SIDE / 2 * self.px, cx + SIDE / 2 * self.px, cy - SIDE / 2 * self.py, cy + SIDE / 2 * self.py

    def inside(self, roi: Roi) -> bool:
        left, right, top, bottom = self.edges(roi)
        return left >= -0.5 and top >= -0.5 and right <= roi[2] - 0.5 and bottom <= roi[3] - 0.5

    def roi(self) -> Roi:
        """A square ROI centred on the grid with MARGIN output pixels around it, its side an even number of px."""
        side = 2 * ceil((SIDE + 2 * MARGIN) * max(self.px, self.py) / 2)
        return round(self.cx - (side - 1) / 2), round(self.cy - (side - 1) / 2), side, side


def sample_grid(frames: torch.Tensor, cx: float, cy: float, px: float, py: float, sub: int) -> torch.Tensor:
    """Bilinear samples of frames (N, H, W) at sub x sub points per output pixel -> (N, SIDE*sub, SIDE*sub).

    (cx, cy) is the grid centre in ROI px; zero outside the ROI.
    """
    height, width = frames.shape[-2:]
    t = (torch.arange(SIDE * sub, dtype=frames.dtype) + 0.5) / sub - SIDE / 2   # output pixels from the centre
    gx = (cx + t * px) / (width - 1) * 2 - 1
    gy = (cy + t * py) / (height - 1) * 2 - 1
    grid_y, grid_x = torch.meshgrid(gy, gx, indexing='ij')
    grid = torch.stack([grid_x, grid_y], -1)[None].expand(len(frames), -1, -1, -1)
    return F.grid_sample(frames[:, None], grid, mode='bilinear', padding_mode='zeros', align_corners=True)[:, 0]


def region16(frames: np.ndarray, grid: Grid, roi: Roi) -> np.ndarray:
    """(N, ROI height, ROI width) -> the (N, 16, 16) output: the grid resampled, then bilinear with antialiasing."""
    t = torch.from_numpy(np.asarray(frames, dtype=np.float32))
    cx, cy = grid.in_roi(roi)
    samples = sample_grid(t, cx, cy, grid.px, grid.py, SUBSAMPLES)
    return F.interpolate(samples[:, None], size=(SIDE, SIDE), mode='bilinear', antialias=True,
                         align_corners=False)[:, 0].numpy()
