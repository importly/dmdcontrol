"""Run.mode kernel: optical convolution data for the EODLA translator model, written batch by batch to data.h5.

Each batch is Run.Kernel.batch_size feature maps convolved with one kernel in one DMD pass.
data.h5 holds, per batch: output (optical result), kernel, input (feature maps) and label.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

import h5py
import numpy as np
import torch
import torchvision.datasets.utils as torchvision_utils
from PIL import Image, ImageDraw

from bcnn import Conv2dEODLA, KernelGen, TranslatorDataGen
from dmdcontrol.runtime import PairRig
from dmdcontrol.utils import CONFIG, progress_bar

log = logging.getLogger('collect')

IN_CHANNELS = OUT_CHANNELS = 1


def _urlretrieve(url: str, filename: str | Path, chunk_size: int = 1024 * 32) -> None:
    """torchvision's dataset download, drawn with the run's rich bar instead of tqdm."""
    request = urllib.request.Request(url, headers={'User-Agent': torchvision_utils.USER_AGENT})
    with urllib.request.urlopen(request) as response, open(filename, 'wb') as file, \
            progress_bar(download=True) as bar:
        task = bar.add_task(f'Downloading {Path(filename).name}', total=response.length)
        while chunk := response.read(chunk_size):
            file.write(chunk)
            bar.advance(task, len(chunk))


torchvision_utils._urlretrieve = _urlretrieve


def collect_kernels(rig: PairRig, run_dir: Path) -> None:
    settings = CONFIG.Run.Kernel
    dataset = TranslatorDataGen(
        train=False,
        download=True,
        dataset_size=settings.dataset_size,
        image_size=settings.image_size,
        kernel_size=settings.kernel_size,
        in_channels=IN_CHANNELS,
        kernel_seed=settings.kernel_seed,
    )
    loader = torch.utils.data.DataLoader(dataset, batch_size=settings.batch_size, shuffle=False,  # pyright: ignore[reportArgumentType]  (duck-typed Dataset)
                                         num_workers=1, drop_last=True)
    kernels = KernelGen(kernel_size=settings.kernel_size, train=True)
    batches = len(loader)
    height, width = rig.camera.ROI_HEIGHT, rig.camera.ROI_WIDTH
    size_gb = batches * settings.batch_size * height * width * 4 / 1e9
    log.info('Collecting %d batches of %d feature maps, output %dx%d (%.1f GB)', batches, settings.batch_size,
             height, width, size_gb)
    if (height, width) == (CONFIG.Camera.height, CONFIG.Camera.width):
        log.warning('Camera.ROI is the full sensor, so data.h5 will be %.0f GB: set the kernel ROI in config.yaml',
                    size_gb)
    
    rng = np.random.default_rng(4)
    # closed on any exit, so a crash leaves the batches written so far readable
    with h5py.File(run_dir / 'data.h5', 'x') as data_file:
        output = data_file.create_dataset(
            'output', (batches, settings.batch_size, OUT_CHANNELS, height, width), np.float32)
        kernel_data = data_file.create_dataset(
            'kernel', (batches, OUT_CHANNELS, IN_CHANNELS, settings.kernel_size, settings.kernel_size), np.float32)
        input_data = data_file.create_dataset(
            'input', (batches, settings.batch_size, IN_CHANNELS, settings.image_size, settings.image_size), np.float32)
        label_data = data_file.create_dataset('label', (batches, settings.batch_size, 3), np.float32)

        # redrawn once a second: the bar's thread shares the GIL with the render thread during a pass
        with progress_bar(refresh_per_second=1) as bar:
            task = bar.add_task('Collecting batches', total=batches)
            for index, (fm, label) in enumerate(loader):
                kernel = kernels.get_kernel(index)
                sheet = run_dir / 'sheets' / f'batch_{index:04d}' if rng.random() < settings.sheet_fraction else None
                result = Conv2dEODLA.apply(fm, kernel, None, 1, [settings.kernel_size // 2] * 2, 1, 1,
                                           rig, OUT_CHANNELS, sheet)
                output[index] = result.cpu().numpy()
                kernel_data[index] = kernel.cpu().numpy().astype(np.float32)
                input_data[index] = fm.cpu().numpy().astype(np.float32)
                label_data[index] = label.cpu().numpy().astype(np.float32)
                if sheet is not None:
                    try:  # a picture must never end a long collection
                        comparison_sheet(sheet.with_name(f'{sheet.name}_compare.png'), fm, kernel, result,
                                         (CONFIG.Camera.ROI.start_x, CONFIG.Camera.ROI.start_y))
                    except Exception as exc:
                        log.warning('Comparison sheet for batch %d skipped: %s', index, exc)
                bar.advance(task)
    log.info('Collection complete: %d batches in %s', batches, run_dir / 'data.h5')


# Where DMD A lands on the sensor, fitted from count digits in 20261102-170126
DMD_CENTRE_ON_SENSOR = (661, 384)       # x, y of DMD pixel (960, 540)
SENSOR_PX_PER_DMD_PX = (0.589, 0.559)   # x, y
PANEL_PX = 120
STRIPS_PER_ROW = 4


def comparison_sheet(path: Path, fm: torch.Tensor, kernel: torch.Tensor, output: torch.Tensor,
                     roi_origin: tuple[int, int]) -> None:
    """One strip per feature map: input | kernel | expected | output | output at 16x16, labelled with r.

    expected is the digital convolution with the kernel rotated 180 degrees (a true convolution,
    which is what the optics compute; F.conv2d alone is cross-correlation). output is the optical
    result cropped to the feature map's footprint on the sensor, then averaged down to expected's
    grid; r is the correlation of those two. Grey panels are each drawn with mid-grey = their mean
    and +-3 standard deviations to white/black.
    """
    settings = CONFIG.Run.Kernel
    expected = torch.nn.functional.conv2d(fm, torch.flip(kernel, (-2, -1)), padding=settings.kernel_size // 2)
    (cx, cy), (sx, sy) = DMD_CENTRE_ON_SENSOR, SENSOR_PX_PER_DMD_PX
    half_w, half_h = settings.fm_px * sx / 2, settings.fm_px * sy / 2
    x0, y0 = max(0, round(cx - roi_origin[0] - half_w)), max(0, round(cy - roi_origin[1] - half_h))
    optical = output[:, 0, y0:y0 + round(2 * half_h), x0:x0 + round(2 * half_w)]
    if optical.numel() == 0:
        raise ValueError(f'the feature map footprint is outside the {output.shape[-1]}x{output.shape[-2]} ROI')
    optical_small = torch.nn.functional.adaptive_avg_pool2d(optical, (expected.shape[-2], expected.shape[-1]))

    def panel(values: torch.Tensor, binary: bool = False) -> Image.Image:
        v = values.detach().cpu().numpy().astype(np.float64)
        if binary:
            pixels = np.where(v > 0, 255, 0)
        else:
            std = v.std() or 1.0
            pixels = np.clip(128 + 127 * (v - v.mean()) / (3 * std), 0, 255)
        return Image.fromarray(pixels.astype(np.uint8), mode='L').resize((PANEL_PX, PANEL_PX), Image.Resampling.NEAREST)

    strip_w, strip_h, label_h, gap = 5 * PANEL_PX + 4 * 4, PANEL_PX, 14, 16
    rows = -(-len(fm) // STRIPS_PER_ROW)
    sheet = Image.new('L', (STRIPS_PER_ROW * (strip_w + gap), 20 + rows * (strip_h + label_h + gap)), 40)
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 4), 'input | kernel | expected (true conv) | output (fm area) | output at 16x16', fill=255)
    for i in range(len(fm)):
        r = np.corrcoef(optical_small[i].flatten().numpy(), expected[i].flatten().numpy())[0, 1]
        x = (i % STRIPS_PER_ROW) * (strip_w + gap)
        y = 20 + (i // STRIPS_PER_ROW) * (strip_h + label_h + gap)
        draw.text((x, y), f'#{i}  r = {r:+.2f}', fill=255)
        for j, image in enumerate((panel(fm[i, 0], binary=True), panel(kernel[0, 0], binary=True),
                                   panel(expected[i, 0]), panel(optical[i]), panel(optical_small[i]))):
            sheet.paste(image, (x + j * (PANEL_PX + 4), y + label_h))
    sheet.save(path)
    log.info('Saved comparison sheet to %s', path)
