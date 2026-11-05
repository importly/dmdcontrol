"""Capture rows of an earlier kernel run again and compare: the same (input, kernel) pairs, light and result.

    uv run python replay.py runs/train_data/emnist_test/20261104-222510 [--rows 440] [--config configs/x.yaml]

Writes runs/tests/replay/<timestamp>/data.h5 with the earlier run's columns (view.py opens it) and logs how
the new captures compare with the old: ON events per px (the light level), and r and SSIM of target16.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from dmdcontrol.laser import Laser
from dmdcontrol.runtime import PairRig
from dmdcontrol.runtime.dmd_conv import TERMS, capture_terms, combine
from dmdcontrol.runtime.output_grid import Grid, region16
from dmdcontrol.utils import CONFIG, WORKSPACE
from dmdcontrol.utils.stop import install as stop_on_signals
from main import setup_logging
from metrics import r as pearson, ssim

log = logging.getLogger('replay')
COLUMNS = ('input16', 'kernel9', 'conv16', 'target16', 'frames', 'label', 'ii', 'kk')


def capture(rig: PairRig, fm: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """The four captures of one pass, redone when there is no light (a check that does not look at the result)."""
    settings = CONFIG.Run.Kernel
    for attempt in range(1, settings.max_attempts + 1):
        terms = capture_terms(rig, fm, kernel)
        if terms.mean() >= settings.min_events_per_px:
            return terms
        log.warning('No light (%.2f ON events per px per capture); redoing the pass (attempt %d of %d)', terms.mean(),
                    attempt + 1, settings.max_attempts)
        rig.reset_dmds()
    raise RuntimeError(f'no light in {settings.max_attempts} tries')


def compare(old: dict[str, np.ndarray], target: np.ndarray, frames: np.ndarray) -> None:
    old_frames, new_frames = old['frames'].astype(np.float64), frames.astype(np.float64)
    ratio = new_frames.mean((1, 2, 3)) / old_frames.mean((1, 2, 3))
    q = lambda v: ' / '.join(f'{np.percentile(v, p):.3f}' for p in (5, 50, 95))
    log.info('Light, ON events per px per capture: earlier %.3f, now %.3f (now / earlier %.3f; per sample 5/50/95%% %s)',
             old_frames.mean(), new_frames.mean(), new_frames.mean() / old_frames.mean(), q(ratio))
    for t, term in enumerate(TERMS):
        log.info('  %s: earlier %.3f, now %.3f', term, old_frames[:, t].mean(), new_frames[:, t].mean())
    r_same = [pearson(a, b) for a, b in zip(target, old['target16'])]
    s_same = [ssim(a, b) for a, b in zip(target, old['target16'])]
    log.info('target16 now vs earlier, per sample: r 5/50/95%% %s (lowest %.3f); SSIM 5/50/95%% %s (lowest %.3f)',
             q(r_same), min(r_same), q(s_same), min(s_same))
    for name, t16 in (('earlier', old['target16']), ('now', target)):
        log.info('target16 vs conv16, %s: median r %.3f, median SSIM %.3f', name,
                 np.median([pearson(a, b) for a, b in zip(t16, old['conv16'])]),
                 np.median([ssim(a, b) for a, b in zip(t16, old['conv16'])]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run', type=Path, help='an earlier kernel run directory, or its data.h5')
    parser.add_argument('--rows', type=int, default=440, help='how many of its first rows to capture again')
    parser.add_argument('--config', type=Path, help='config file to use instead of config.yaml')
    args = parser.parse_args()

    old_path = args.run / 'data.h5' if args.run.is_dir() else args.run
    with h5py.File(old_path, 'r') as f:
        n = min(args.rows, f['frames'].shape[0])
        old = {c: f[c][:n] for c in COLUMNS}
        attrs = dict(f.attrs)
    roi = tuple(int(v) for v in attrs['roi'])
    camera = CONFIG.Camera
    if roi != (camera.ROI.start_x, camera.ROI.start_y, camera.ROI.width, camera.ROI.height):
        sys.exit(f'the earlier run used Camera.ROI {roi}; set the config to it')
    if attrs['polarity_mode'] != camera.Accumulation.polarity_mode or attrs['polarity_mode'] != 'positive':
        sys.exit('replay compares ON-event (positive) runs only')
    grid, gamma = Grid(*attrs['grid_centre'], *attrs['grid_px']), float(attrs['gamma'])

    run_dir = WORKSPACE / 'runs' / 'tests' / 'replay' / f'{datetime.now():%Y%m%d-%H%M%S}'
    run_dir.mkdir(parents=True)
    setup_logging(run_dir)
    stop_on_signals()
    log.info('Capturing the first %d rows of %s again', n, old_path)

    batch = CONFIG.Run.Kernel.batch_size
    with Laser(), PairRig() as rig:
        terms = np.concatenate([capture(rig, old['input16'][i:i + batch], old['kernel9'][i:i + batch])
                                for i in range(0, n, batch)], axis=1)
    target = region16(combine(terms, gamma), grid, roi).astype(np.float32)
    frames = np.clip(np.rint(terms), 0, 255).astype(np.uint8).transpose(1, 0, 2, 3)

    with h5py.File(run_dir / 'data.h5', 'x') as f:
        for c in COLUMNS:
            if c == 'frames':
                f.create_dataset(c, data=frames, chunks=(1, *frames.shape[1:]), compression='lzf')
            else:
                f[c] = target if c == 'target16' else old[c]
        f.attrs.update(attrs)
        f.attrs.update({'replay_of': str(old_path), 'created': datetime.now().isoformat(timespec='seconds')})
    log.info('Saved %s', run_dir / 'data.h5')
    compare(old, target, frames)


if __name__ == '__main__':
    main()
