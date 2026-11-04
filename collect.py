"""Run.mode kernel: real optical convolutions for the EODLA translator model, one row per sample in data.h5.

16x16 in, 16x16 out: a binary CNN stacks these layers, so each output lands on the input's own
16x16 grid - the zero-padded 'same' convolution. Each sample is a 16x16 input on DMD A and a
9x9 kernel on DMD B (operands.py), each pixel a square of Run.Kernel.mirrors_per_px mirrors. One
DMD pass captures Run.Kernel.batch_size samples, each as four captures (TERMS).

data.h5, one row per sample (the translator's gen16_<split>.h5 names where it has the column):
  input16, kernel9   the operands, +-1
  conv16             their digital same convolution, 16x16, kernel flipped: a true convolution,
                     which is what the optics compute (the translator's data.make_conv)
  target16           the optical result: the four captures combined (dmd_conv.combine), then the
                     output grid (Run.Kernel.grid_centre / grid_px) made 16x16 by output_grid.region16,
                     the same steps as the translator's simulator
  frames             the four raw captures over the whole ROI, event counts in TERMS order: uint8
                     (positive polarity, clipped at 255 with a warning) or int16 (signed)
  label, ii, kk      the input's label [class, source, index], its index in its dataset, and the
                     kernel's row in kernels.npz
Rows are appended one pass at a time, so a crash leaves only complete rows. The attributes record
the kernels file and its sha256, train or test, sources, seed, ROI, grid, mirrors per pixel and gamma.
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from math import ceil
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw

from calibrate import fit_grid, grid_report
from dmdcontrol.runtime import PairRig
from dmdcontrol.runtime.dmd_conv import TERMS, capture_terms, combine, save_sheets
from dmdcontrol.runtime.output_grid import SIDE, Grid, region16
from dmdcontrol.utils import CONFIG, WORKSPACE, progress_bar
from dmdcontrol.utils.stop import deferred
from operands import load_inputs, load_kernels

log = logging.getLogger('collect')


def same_conv(fm: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Per-sample zero-padded same convolution of fm (N, h, w) with kernel (N, kh, kw) -> (N, h, w).

    The kernel is flipped, so this is a true convolution (F.conv2d alone is cross-correlation),
    the same as the translator's data.make_conv.
    """
    x = torch.from_numpy(np.asarray(fm, dtype=np.float32))
    w = torch.from_numpy(np.asarray(kernel, dtype=np.float32)).flip(-1, -2)
    return F.conv2d(x[None], w[:, None], padding=(w.shape[-2] // 2, w.shape[-1] // 2), groups=len(x))[0].numpy()


def collect_kernels(rig: PairRig, run_dir: Path) -> None:
    settings = CONFIG.Run.Kernel
    count = settings.dataset_size
    batches = ceil(count / settings.batch_size)

    height, width = rig.camera.ROI_HEIGHT, rig.camera.ROI_WIDTH
    roi = (CONFIG.Camera.ROI.start_x, CONFIG.Camera.ROI.start_y, width, height)
    grid = Grid.configured()
    if not grid.inside(roi):
        sx, sy, w, h = grid.roi()
        raise ValueError(f'the {SIDE}x{SIDE} output grid (Run.Kernel.grid_centre / grid_px) is not inside Camera.ROI '
                         f'{roi}: use start_x {sx}, start_y {sy}, width {w}, height {h}')
    # ON-only counts are small and never negative: one byte each halves a week's disk; signed needs int16
    signed = CONFIG.Camera.Accumulation.polarity_mode == 'signed'
    frame_dtype, frame_max = (np.int16, 32767) if signed else (np.uint8, 255)
    size_gb = count * len(TERMS) * height * width * np.dtype(frame_dtype).itemsize / 1e9
    free_gb = shutil.disk_usage(run_dir).free / 1e9
    sets = 'train' if settings.train else 'test'
    sources = ', '.join(f'{name} {share:g}' for name, share in settings.sources.items() if share)
    log.info('Collecting %d samples (%d passes of up to %d) from the %s sets (%s), seed %d; ROI %dx%d, output '
             'grid centred at (%.1f, %.1f), %.2f x %.2f camera px per output px; raw captures %.1f GB before '
             'compression, %.0f GB free', count, batches, settings.batch_size, sets, sources, settings.seed,
             width, height, grid.cx, grid.cy, grid.px, grid.py, size_gb, free_gb)
    if free_gb < size_gb / 3:  # lzf leaves event counts a few times smaller, not more
        raise RuntimeError(f'{free_gb:.0f} GB free for {size_gb:.0f} GB of raw captures before compression: '
                           'lower Run.Kernel.dataset_size or free some disk')
    if free_gb < size_gb:
        log.warning('%.0f GB free and %.0f GB of raw captures before compression: watch the disk', free_gb, size_gb)

    rng = np.random.default_rng(settings.seed)
    kernels, kk, kernels_sha256 = load_kernels(WORKSPACE / settings.kernels, settings.seed, count, rng)
    inputs, labels = load_inputs(count, settings.sources, settings.train, rng)
    with_sheets = rng.random(batches) < settings.sheet_fraction
    log.info('Loaded %d inputs and %d kernels (block %d of %s)', len(inputs), len(kernels), settings.seed,
             settings.kernels)

    columns = {'input16': ((SIDE, SIDE), np.float32),
               'kernel9': ((9, 9), np.float32),
               'conv16': ((SIDE, SIDE), np.float32),
               'target16': ((SIDE, SIDE), np.float32),
               'frames': ((len(TERMS), height, width), frame_dtype),
               'label': ((3,), np.float32),
               'ii': ((), np.int32),
               'kk': ((), np.int32)}
    # closed on any exit; rows go in a pass at a time, so a crash leaves only complete ones
    with h5py.File(run_dir / 'data.h5', 'x') as data_file:
        for name, (shape, dtype) in columns.items():
            data_file.create_dataset(name, (0, *shape), dtype, maxshape=(None, *shape),
                                     chunks=(1, *shape) if name == 'frames' else (settings.batch_size, *shape),
                                     compression='lzf' if name == 'frames' else None)
        data_file.attrs.update({
            'kernels': settings.kernels, 'kernels_sha256': kernels_sha256, 'train': settings.train,
            'sources': json.dumps(settings.sources), 'seed': settings.seed,
            'mirrors_per_px': settings.mirrors_per_px, 'gamma': settings.gamma, 'roi': roi,
            'grid_centre': (grid.cx, grid.cy), 'grid_px': (grid.px, grid.py), 'terms': ', '.join(TERMS),
            'polarity_mode': CONFIG.Camera.Accumulation.polarity_mode,
            'window_us': CONFIG.Camera.Accumulation.window_us,
            'conv16': 'same, zero padded, kernel flipped (true convolution)',
            'target16': 'frames combined (pp - pn - np + nn, each ** gamma); the output grid resampled bilinearly '
                        'to 192x192, then bilinear with antialias to 16x16 (output_grid.region16)',
            'created': datetime.now().isoformat(timespec='seconds'),
        })

        # redrawn once a second: the bar's thread shares the GIL with the render thread during a pass
        events: list[float] = []  # mean ON events per px per capture of each pass
        with progress_bar(refresh_per_second=1) as bar:
            task = bar.add_task('Collecting batches', total=batches)
            for index in range(batches):
                started = time.monotonic()
                rows = slice(index * settings.batch_size, (index + 1) * settings.batch_size)
                fm, kernel = inputs[rows], kernels[rows]
                terms = capture_terms(rig, fm, kernel)
                for attempt in range(2, settings.max_attempts + 1):
                    if terms.mean() >= settings.min_events_per_px:
                        break
                    log.warning('Batch %d: %.2f ON events per px per capture, under %g: no light (laser off?), '
                                'redoing the pass (attempt %d of %d)', index, terms.mean(),
                                settings.min_events_per_px, attempt, settings.max_attempts)
                    terms = capture_terms(rig, fm, kernel)
                if terms.mean() < settings.min_events_per_px:
                    raise RuntimeError(f'no light in {settings.max_attempts} tries of batch {index} '
                                       f'({terms.mean():.2f} ON events per px per capture): laser off?')
                events.append(float(terms.mean()))
                if abs(events[-1] / np.median(events) - 1) > 0.1:
                    log.warning('Batch %d: %.2f ON events per px per capture, %+.0f%% from the run so far: the light '
                                'changed', index, events[-1], 100 * (events[-1] / np.median(events) - 1))
                output = combine(terms, settings.gamma)
                conv, target = same_conv(fm, kernel), region16(output, grid, roi)
                counts = np.rint(terms)
                if (clipped := int((counts > frame_max).sum())):
                    log.warning('Batch %d: %d pixels over %d events clipped in the stored frames (target16 is not)',
                                index, clipped, frame_max)
                with deferred():  # a stop signal waits until the pass is written
                    _append(data_file, {
                        'input16': fm, 'kernel9': kernel, 'conv16': conv, 'target16': target,
                        'frames': np.clip(counts, -frame_max - 1, frame_max).astype(frame_dtype).transpose(1, 0, 2, 3),
                        'label': labels[rows], 'ii': labels[rows, 2], 'kk': kk[rows]})
                    data_file.flush()  # a hard crash keeps every finished pass
                if with_sheets[index]:
                    sheet = run_dir / 'sheets' / f'batch_{index:04d}'
                    try:  # a picture must never end a long collection
                        save_sheets(rig.camera, terms, output, sheet)
                        comparison_sheet(sheet.with_name(f'{sheet.name}_compare.png'), fm, kernel, conv, target,
                                         output, grid, roi)
                    except Exception as exc:
                        log.warning('Sheets for batch %d skipped: %s', index, exc)
                if index == 0:
                    check_grid(output, conv, grid, roi)
                # one line per pass, so drift in the optics or the laser shows up in run.log
                r = np.median([np.corrcoef(t.ravel(), c.ravel())[0, 1] for t, c in zip(target, conv)])
                log.info('Batch %d/%d: median r(target16, conv16) %.3f, %.2f ON events per px per capture, %.1f s',
                         index + 1, batches, r, events[-1], time.monotonic() - started)
                bar.advance(task)
    log.info('Collection complete: %d samples in %s', count, run_dir / 'data.h5')


def _append(data_file: h5py.File, values: dict[str, np.ndarray]) -> None:
    for name, value in values.items():
        dataset = data_file[name]
        assert isinstance(dataset, h5py.Dataset)
        start = dataset.shape[0]
        dataset.resize(start + len(value), axis=0)
        dataset[start:] = value


def check_grid(output: np.ndarray, conv: np.ndarray, grid: Grid, roi: tuple[int, int, int, int]) -> None:
    """Re-fit the output grid on this batch; warn with the config to use if it moved."""
    try:
        fit = fit_grid(output, conv, grid, roi)
    except Exception as exc:
        log.warning('Grid fit skipped: %s', exc)
        return
    line, warning = grid_report(fit, grid, roi)
    log.info('Batch 0 grid fit: %s', line)
    if warning:
        log.warning(warning)


PANEL_PX = 120
STRIPS_PER_ROW = 4


def comparison_sheet(path: Path, fm: np.ndarray, kernel: np.ndarray, conv: np.ndarray, target: np.ndarray,
                     output: np.ndarray, grid: Grid, roi: tuple[int, int, int, int]) -> None:
    """One strip per sample: input | kernel | conv16 (digital) | target16 (optical) | the ROI with the grid outlined.

    Labelled with r, the correlation of target16 with conv16. Grey panels are each drawn with
    mid-grey = their mean and +-3 standard deviations to white/black.
    """
    left, right, top, bottom = grid.edges(roi)

    def panel(values: np.ndarray, binary: bool = False, outline: bool = False) -> Image.Image:
        v = np.asarray(values, dtype=np.float64)
        if binary:
            pixels = np.where(v > 0, 255, 0)
        else:
            std = v.std() or 1.0
            pixels = np.clip(128 + 127 * (v - v.mean()) / (3 * std), 0, 255)
        resample = Image.Resampling.NEAREST if v.shape[-1] < PANEL_PX else Image.Resampling.BOX
        image = Image.fromarray(pixels.astype(np.uint8), mode='L').resize((PANEL_PX, PANEL_PX), resample)
        if outline:
            sx, sy = PANEL_PX / v.shape[-1], PANEL_PX / v.shape[-2]
            ImageDraw.Draw(image).rectangle(((left + 0.5) * sx, (top + 0.5) * sy, (right + 0.5) * sx,
                                             (bottom + 0.5) * sy), outline=255)
        return image

    strip_w, strip_h, label_h, gap = 5 * PANEL_PX + 4 * 4, PANEL_PX, 14, 16
    rows = -(-len(fm) // STRIPS_PER_ROW)
    sheet = Image.new('L', (STRIPS_PER_ROW * (strip_w + gap), 20 + rows * (strip_h + label_h + gap)), 40)
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 4), 'input | kernel | conv16 (digital) | target16 (optical) | ROI, output grid outlined', fill=255)
    for i in range(len(fm)):
        r = np.corrcoef(target[i].ravel(), conv[i].ravel())[0, 1]
        x = (i % STRIPS_PER_ROW) * (strip_w + gap)
        y = 20 + (i // STRIPS_PER_ROW) * (strip_h + label_h + gap)
        draw.text((x, y), f'#{i}  r = {r:+.2f}', fill=255)
        for j, image in enumerate((panel(fm[i], binary=True), panel(kernel[i], binary=True), panel(conv[i]),
                                   panel(target[i]), panel(output[i], outline=True))):
            sheet.paste(image, (x + j * (PANEL_PX + 4), y + label_h))
    sheet.save(path)
    log.info('Saved comparison sheet to %s', path)
