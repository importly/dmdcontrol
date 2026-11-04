"""Step through a kernel run's data.h5 one sample at a time.

    uv run python view.py runs/<output_root>/<run> [--sample N] [--save out.png]

Keys: left / right one sample, up / down ten, home / end first / last.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h5py
import matplotlib
import numpy as np

from dmdcontrol.runtime.dmd_conv import TERMS, combine
from dmdcontrol.runtime.output_grid import SIDE, Grid

GRID_COLOUR = 'tab:orange'


class RunData:
    """A run's data.h5, read one sample at a time."""

    def __init__(self, path: Path):
        self.path = path / 'data.h5' if path.is_dir() else path
        self.name = self.path.parent.name
        self.file = h5py.File(self.path, 'r')
        attrs = self.file.attrs
        self.roi = tuple(int(v) for v in np.asarray(attrs['roi']))
        (cx, cy), (px, py) = np.asarray(attrs['grid_centre'], float), np.asarray(attrs['grid_px'], float)
        self.grid = Grid(cx, cy, px, py)
        self.gamma = float(np.asarray(attrs['gamma']))
        self.split = str(attrs['split'])
        self.count = self.file['frames'].shape[0]

    def sample(self, i: int) -> dict[str, np.ndarray]:
        names = ('input16', 'kernel9', 'conv16', 'target16', 'frames', 'label', 'ii', 'kk')
        return {name: np.asarray(self.file[name][i]) for name in names}


def _signed(ax, values: np.ndarray, title: str) -> None:
    limit = float(np.abs(values).max()) or 1.0
    ax.imshow(values, cmap='gray', vmin=-limit, vmax=limit, interpolation='nearest')
    ax.set_title(f'{title}\n[{values.min():.4g}, {values.max():.4g}]', fontsize=9)


def _binary(ax, values: np.ndarray, title: str) -> None:
    ax.imshow(values, cmap='gray', vmin=-1, vmax=1, interpolation='nearest')
    ax.set_title(f'{title}\n{values.shape[0]}x{values.shape[1]}, +-1', fontsize=9)


def _grid(ax, run: RunData, cells: bool) -> None:
    left, right, top, bottom = run.grid.edges(run.roi)
    if cells:
        inner = range(1, SIDE)
        ax.vlines([left + j * run.grid.px for j in inner], top, bottom, color=GRID_COLOUR, lw=0.8, alpha=0.5)
        ax.hlines([top + j * run.grid.py for j in inner], left, right, color=GRID_COLOUR, lw=0.8, alpha=0.5)
    ax.plot([left, right, right, left, left], [top, top, bottom, bottom, top], color=GRID_COLOUR, lw=1.0)


LAYOUT = [['input', 'kernel', 'roi', 'roi', 'term0', 'term1'],
          ['conv', 'target', 'roi', 'roi', 'term2', 'term3']]


def draw(fig, axes: dict, run: RunData, i: int) -> None:
    s = run.sample(i)
    frames = s['frames'].astype(np.float64)
    combined = combine(frames, run.gamma)
    r = np.corrcoef(s['target16'].ravel(), s['conv16'].ravel())[0, 1]
    for ax in axes.values():
        ax.clear()
        ax.set_xticks([])
        ax.set_yticks([])

    _binary(axes['input'], s['input16'], 'input16 (DMD A)')
    _binary(axes['kernel'], s['kernel9'], 'kernel9 (DMD B)')
    _signed(axes['conv'], s['conv16'], 'conv16 (digital)')
    _signed(axes['target'], s['target16'], f'target16 (optical), r = {r:+.3f}')
    _signed(axes['roi'], combined, f'captures combined, full ROI {run.roi[2]}x{run.roi[3]} px, output grid')
    _grid(axes['roi'], run, cells=True)

    low, high = min(0.0, float(frames.min())), float(frames.max()) or 1.0
    for ax, term, frame in zip((axes[f'term{j}'] for j in range(len(TERMS))), TERMS, frames):
        ax.imshow(frame, cmap='gray', vmin=low, vmax=high, interpolation='nearest')
        ax.set_title(f'{term}: {frame.mean():.2f} events/px, max {frame.max():.0f}', fontsize=9)
        _grid(ax, run, cells=False)

    label = ', '.join(f'{v:g}' for v in s['label'])
    fig.suptitle(f'{run.name}   sample {i} of {run.count} (0-based)   {run.split} rows: input {int(s["ii"])}, '
                 f'kernel {int(s["kk"])}   label [{label}]   gamma {run.gamma:g}', fontsize=10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('run', type=Path, help='a run directory, or its data.h5')
    parser.add_argument('--sample', type=int, default=0, help='sample to start at (0-based)')
    parser.add_argument('--save', type=Path, help='write this sample to a PNG instead of opening a window')
    args = parser.parse_args()

    if args.save:
        matplotlib.use('Agg')
    # free the arrow and home keys for paging
    for keymap in ('keymap.back', 'keymap.forward', 'keymap.home'):
        matplotlib.rcParams[keymap] = [k for k in matplotlib.rcParams[keymap] if k not in ('left', 'right', 'home')]
    import matplotlib.pyplot as plt

    run = RunData(args.run)
    if run.count == 0:
        raise SystemExit(f'{run.path} has no samples yet')
    state = {'i': min(max(args.sample, 0), run.count - 1)}

    fig, axes = plt.subplot_mosaic(LAYOUT, figsize=(18, 7.6), layout='constrained')
    draw(fig, axes, run, state['i'])

    if args.save:
        fig.savefig(args.save, dpi=110)
        print(f'Saved sample {state["i"]} to {args.save}')
        return

    steps = {'right': 1, 'left': -1, 'up': 10, 'down': -10}

    def on_key(event) -> None:
        if event.key in steps:
            i = state['i'] + steps[event.key]
        elif event.key == 'home':
            i = 0
        elif event.key == 'end':
            i = run.count - 1
        else:
            return
        i = min(max(i, 0), run.count - 1)
        if i != state['i']:
            state['i'] = i
            draw(fig, axes, run, i)
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect('key_press_event', on_key)
    plt.show()


if __name__ == '__main__':
    main()
