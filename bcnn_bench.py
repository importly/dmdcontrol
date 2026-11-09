"""Run saved binary CNNs (the translator repo's scripts/bcnn_try.py --save) on the bench, next to ideal conv.

    uv run python bcnn_bench.py datasets/bcnn/test.npz datasets/bcnn/bcnn_try_conv.pt datasets/bcnn/bcnn_try_A.pt
        [--images 2048] [--config configs/x.yaml] [--dry] [--resume runs/tests/bcnn_bench/<earlier>]

Each 9x9 layer is one optical convolution per (image, output channel, input channel), min-max normalised per
sample as the translator predicts and summed over input channels, with the model's bias, skip connections,
per-batch normalisation (batches of 256, as bcnn_try evaluates) and readout. All models share each layer's passes
(one kernel per sample). test.npz holds x (N, 16, 16) +-1 and y; its order sets the normalisation batches. --dry
skips the bench (ideal conv only). Writes runs/tests/bcnn_bench/<timestamp>/layer<i>.npz after each layer
(inputs, kernels, target16, conv16, model index: translator training rows) and logs each model's accuracy.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime
from math import ceil
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from dmdcontrol.utils import CONFIG, WORKSPACE

log = logging.getLogger('bcnn_bench')
BN_BATCH = 256


def sign(v: torch.Tensor) -> torch.Tensor:
    return torch.where(v >= 0, 1.0, -1.0)


def bn_sign(h: torch.Tensor) -> torch.Tensor:
    """A layer's input: sign(batch_norm(h)), per channel, over consecutive batches of BN_BATCH images."""
    return torch.cat([sign(F.batch_norm(h[s:s + BN_BATCH], None, None, training=True))
                      for s in range(0, len(h), BN_BATCH)])


def minmax(t: torch.Tensor) -> torch.Tensor:
    lo, hi = t.amin((-2, -1), keepdim=True), t.amax((-2, -1), keepdim=True)
    return (t - lo) / (hi - lo + 1e-12)


def ideal(z: torch.Tensor, k: torch.Tensor) -> torch.Tensor:
    """True 'same' convolution of each map with its own kernel: (N, 16, 16), (N, 9, 9)."""
    return F.conv2d(z[None], k.flip(-1, -2)[:, None], padding=4, groups=len(z))[0]


def layer_weights(model: dict, i: int) -> tuple[torch.Tensor, torch.Tensor]:
    """Layer i's +-1 kernels (Cout, Cin, 9, 9) and bias (Cout,); also reads bcnn_try's older 1-channel format."""
    sd = model['state_dict']
    w = sd[f'w.{i}'] if f'w.{i}' in sd else sd['w'][i][None, None]
    return sign(w), sd['b'][i] if sd['b'].dim() == 2 else sd['b'][i:i + 1]


def pairs(h: torch.Tensor, k: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """Every (image, out, in) operand pair of a layer, flattened in that order: maps (N, 16, 16), kernels (N, 9, 9)."""
    z, n, cout, cin = bn_sign(h), len(h), k.shape[0], k.shape[1]
    return (z[:, None].expand(n, cout, cin, 16, 16).reshape(-1, 16, 16),
            k[None].expand(n, cout, cin, 9, 9).reshape(-1, 9, 9))


def finish(out: torch.Tensor, h: torch.Tensor, k: torch.Tensor, b: torch.Tensor, i: int) -> torch.Tensor:
    """Normalised optical outputs of a layer's pairs -> the next running sum (bias, sum over in, skip)."""
    o = out.view(len(h), k.shape[0], k.shape[1], 16, 16).sum(2) + b[None, :, None, None]
    return o if i == 0 else o + h


def readout(model: dict, h: torch.Tensor) -> torch.Tensor:
    p, sd = F.max_pool2d(h, 2), model['state_dict']
    if model['args']['head'] == 'mask':
        return sd['scale'] * torch.einsum('bij,kij->bk', p[:, 0], sd['masks']) / 64
    return p.flatten(1) @ sd['fc.weight'].T + sd['fc.bias']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('test', type=Path)
    parser.add_argument('models', type=Path, nargs='+')
    parser.add_argument('--images', type=int, default=2048, help='first N test images (whole batches of 256)')
    parser.add_argument('--config', type=Path, help='config file to use instead of config.yaml')
    parser.add_argument('--dry', action='store_true', help='ideal conv only, no bench')
    parser.add_argument('--resume', type=Path, help='an earlier run dir: its layer<i>.npz bench outputs are reused')
    args = parser.parse_args()

    d = np.load(args.test)
    n = min(args.images, len(d['y'])) // BN_BATCH * BN_BATCH
    x, y = torch.from_numpy(d['x'][:n]).float()[:, None], torch.from_numpy(d['y'][:n]).long()
    names = [p.stem for p in args.models]
    models = [torch.load(p, map_location='cpu') for p in args.models]
    for name, m in zip(names, models):
        if m['args']['batch'] != BN_BATCH:
            raise SystemExit(f'{name} was evaluated with batches of {m["args"]["batch"]}, not {BN_BATCH}')
    convs = sum(n * layer_weights(m, i)[0].shape[:2].numel() for m in models for i in range(3))

    run_dir = WORKSPACE / 'runs' / 'tests' / 'bcnn_bench' / f'{datetime.now():%Y%m%d-%H%M%S}'
    run_dir.mkdir(parents=True)
    from main import setup_logging
    setup_logging(run_dir)
    log.info('%d test images (%d letters), models %s: %d optical convolutions, %d passes%s', n, int(y.sum()), names,
             convs, ceil(convs / CONFIG.Run.Kernel.batch_size), ' (dry: no bench)' if args.dry else '')

    with torch.no_grad():
        h_ideal = {name: x.clone() for name in names}
        for i in range(3):
            for name, m in zip(names, models):
                k, b = layer_weights(m, i)
                z, kf = pairs(h_ideal[name], k)
                h_ideal[name] = finish(minmax(ideal(z, kf)), h_ideal[name], k, b, i)
        for name, m in zip(names, models):
            log.info('%s on ideal conv: accuracy %.4f', name, (readout(m, h_ideal[name]).argmax(1) == y).float().mean())
        if args.dry:
            return

        from dmdcontrol.laser import Laser
        from dmdcontrol.runtime import PairRig
        from dmdcontrol.runtime.dmd_conv import combine
        from dmdcontrol.runtime.output_grid import Grid, region16
        from dmdcontrol.utils.stop import install as stop_on_signals
        from metrics import r as pearson, ssim
        from replay import capture

        stop_on_signals()
        grid, gamma, batch = Grid.configured(), CONFIG.Run.Kernel.gamma, CONFIG.Run.Kernel.batch_size
        roi = (CONFIG.Camera.ROI.start_x, CONFIG.Camera.ROI.start_y, CONFIG.Camera.ROI.width, CONFIG.Camera.ROI.height)
        h = {name: x.clone() for name in names}
        with Laser(), PairRig() as rig:
            for i in range(3):
                weights = [layer_weights(m, i) for m in models]
                parts = [pairs(h[name], k) for name, (k, _) in zip(names, weights)]
                z, kf = torch.cat([p[0] for p in parts]), torch.cat([p[1] for p in parts])
                sizes = [len(p[0]) for p in parts]
                log.info('Layer %d: %d optical convolutions, %d passes', i + 1, len(z), ceil(len(z) / batch))
                fm, kern = z.numpy().astype(np.float32), kf.numpy().astype(np.float32)
                done = args.resume / f'layer{i + 1}.npz' if args.resume else None
                if done is not None and done.exists():
                    with np.load(done) as f:
                        if not (np.array_equal(f['input16'], fm) and np.array_equal(f['kernel9'], kern)):
                            raise SystemExit(f'{done} holds other operands: not the same test images and models')
                        target = torch.from_numpy(f['target16'])
                    log.info('Layer %d: bench outputs from %s', i + 1, done)
                else:  # 16x16 per pass: a whole layer's raw captures do not fit in memory
                    target = torch.from_numpy(np.concatenate([
                        region16(combine(capture(rig, fm[s:s + batch], kern[s:s + batch]), gamma), grid, roi)
                        for s in range(0, len(fm), batch)]).astype(np.float32))
                conv = ideal(z, kf)
                np.savez_compressed(run_dir / f'layer{i + 1}.npz', input16=fm.astype(np.int8),
                                    kernel9=kern.astype(np.int8), target16=target.numpy(), conv16=conv.numpy(),
                                    model=np.repeat(np.arange(len(names)), sizes),
                                    label=np.concatenate([np.repeat(y.numpy(), s // n) for s in sizes]),
                                    names=np.array(names))
                start = 0
                for name, (k, b), size in zip(names, weights, sizes):
                    rows = slice(start, start + size)
                    start += size
                    h[name] = finish(minmax(target[rows]), h[name], k, b, i)
                    t16, c16 = target[rows].numpy(), conv[rows].numpy()
                    log.info('  %s layer %d: bench vs ideal conv on the same inputs, median r %.3f, SSIM %.3f', name,
                             i + 1, np.median([pearson(a, c) for a, c in zip(t16, c16)]),
                             np.median([ssim(a, c) for a, c in zip(t16, c16)]))
        for name, m in zip(names, models):
            log.info('%s ON THE BENCH: accuracy %.4f (ideal conv %.4f)', name,
                     (readout(m, h[name]).argmax(1) == y).float().mean(),
                     (readout(m, h_ideal[name]).argmax(1) == y).float().mean())
    log.info('Saved %s', run_dir)


if __name__ == '__main__':
    main()
