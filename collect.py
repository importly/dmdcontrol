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
                bar.advance(task)
    log.info('Collection complete: %d batches in %s', batches, run_dir / 'data.h5')
