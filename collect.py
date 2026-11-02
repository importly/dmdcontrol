"""Run.mode kernel: optical convolution data for the EODLA translator model, written batch by batch to data.h5.

Each batch is Run.Kernel.batch_size feature maps convolved with one kernel in one DMD pass.
data.h5 holds, per batch: output (optical result), kernel, input (feature maps) and label.
"""

from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
import torch
from tqdm import tqdm

from bcnn import Conv2dEODLA, KernelGen, TranslatorDataGen
from dmdcontrol.runtime import PairRig
from dmdcontrol.utils import CONFIG

log = logging.getLogger('collect')

IN_CHANNELS = OUT_CHANNELS = 1


def collect_kernels(rig: PairRig, run_dir: Path) -> None:
    settings = CONFIG.Run.Kernel
    dataset = TranslatorDataGen(
        train=True,
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

    rng = np.random.default_rng()
    # closed on any exit, so a crash leaves the batches written so far readable
    with h5py.File(run_dir / 'data.h5', 'x') as data_file:
        output = data_file.create_dataset(
            'output', (batches, settings.batch_size, OUT_CHANNELS, height, width), np.float32)
        kernel_data = data_file.create_dataset(
            'kernel', (batches, OUT_CHANNELS, IN_CHANNELS, settings.kernel_size, settings.kernel_size), np.float32)
        input_data = data_file.create_dataset(
            'input', (batches, settings.batch_size, IN_CHANNELS, settings.image_size, settings.image_size), np.float32)
        label_data = data_file.create_dataset('label', (batches, settings.batch_size, 3), np.float32)

        for index, (fm, label) in tqdm(enumerate(loader), total=batches):
            kernel = kernels.get_kernel(index)
            sheet = run_dir / 'sheets' / f'batch_{index:04d}' if rng.random() < settings.sheet_fraction else None
            result = Conv2dEODLA.apply(fm, kernel, None, 1, [settings.kernel_size // 2] * 2, 1, 1,
                                       rig, OUT_CHANNELS, sheet)
            output[index] = result.cpu().numpy()
            kernel_data[index] = kernel.cpu().numpy().astype(np.float32)
            input_data[index] = fm.cpu().numpy().astype(np.float32)
            label_data[index] = label.cpu().numpy().astype(np.float32)
    log.info('Collection complete: %d batches in %s', batches, run_dir / 'data.h5')
