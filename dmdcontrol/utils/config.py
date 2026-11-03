"""config.yaml, loaded once into typed sections: CONFIG.Run, CONFIG.Laser, CONFIG.Camera, CONFIG.DMD.

Every key in the file must be a field here and every field without a default must be in the
file, so a typo or a leftover key fails at import instead of silently falling back.
"""

from dataclasses import MISSING, dataclass, fields, is_dataclass
from typing import Any

import yaml

from .env import WORKSPACE

CONFIG_PATH = WORKSPACE / "config.yaml"


@dataclass(frozen=True)
class CountConfig:
    start: int
    end: int
    number_size_px: int
    cycles: int
    test_b: str               # dot | checkerboard
    b_dot_x: int
    b_dot_y: int
    b_dot_radius: int


@dataclass(frozen=True)
class KernelConfig:
    operands: str             # the translator's operands.npz, relative to the repo
    split: str                # train | val | test
    seed: int | None
    dataset_size: int
    batch_size: int
    mirrors_per_px: int
    grid_centre: list[float]  # sensor px (x, y) of the output grid's centre
    grid_px: list[float]      # camera px per output pixel (x, y)
    gamma: float
    sheet_fraction: float
    max_attempts: int

    def __post_init__(self):
        if self.split not in ('train', 'val', 'test'):
            raise ValueError(f'config.yaml Run.Kernel.split must be train, val or test, got {self.split!r}')
        if self.mirrors_per_px < 1:
            raise ValueError(f'config.yaml Run.Kernel.mirrors_per_px must be at least 1, got {self.mirrors_per_px}')
        if len(self.grid_centre) != 2 or len(self.grid_px) != 2 or min(self.grid_px) <= 0:
            raise ValueError('config.yaml Run.Kernel.grid_centre and grid_px must each be [x, y], grid_px positive')


@dataclass(frozen=True)
class RunConfig:
    mode: str                 # count | kernel
    output_root: str
    time_max_s: float
    Count: CountConfig
    Kernel: KernelConfig

    def __post_init__(self):
        if self.mode not in ('count', 'kernel'):
            raise ValueError(f'config.yaml Run.mode must be count or kernel, got {self.mode!r}')


@dataclass(frozen=True)
class LaserConfig:
    control: bool
    port: str
    power_mw: float


@dataclass(frozen=True)
class RoiConfig:
    start_x: int
    start_y: int
    width: int
    height: int


@dataclass(frozen=True)
class TriggerInConfig:
    rising_edge: bool
    falling_edge: bool


@dataclass(frozen=True)
class FilterConfig:
    enable: bool
    background_activity_duration: int


@dataclass(frozen=True)
class AccumulationConfig:
    window_us: int
    start_time_offset_us: int
    polarity_mode: str        # positive | signed


@dataclass(frozen=True)
class BiasConfig:             # Prophesee Gen4.1 absolute values, set in this order
    bias_diff: int
    bias_diff_on: int
    bias_diff_off: int
    bias_fo: int
    bias_hpf: int
    bias_refr: int


@dataclass(frozen=True)
class CameraConfig:
    ROI: RoiConfig
    Trigger: TriggerInConfig  # DAVIS
    Filter: FilterConfig      # DAVIS
    Accumulation: AccumulationConfig
    width: int                # DAVIS sensor size
    height: int
    signal_fraction: float
    normalize_scale_max: int
    bias_sensitivity: str     # DAVIS
    Biases: BiasConfig        # Prophesee
    slice_duration_us: int = 10_000


@dataclass(frozen=True)
class DmdPortConfig:
    usb_bus: int
    usb_port: int | list[int]
    xrandr_output: str


@dataclass(frozen=True)
class TriggerOutConfig:
    pulse_width_us: int
    rising_delay_us: int


@dataclass(frozen=True)
class DmdConfig:
    A: DmdPortConfig
    B: DmdPortConfig
    width: int
    height: int
    offset: list[int]
    target_hz: int
    safe_margin_us: float
    min_exposure_us: int
    frame_utilization: float
    dual_pixel: bool
    exposure_us: int
    display_pipeline_vsyncs: int
    paired_startup_leader_vsyncs: int
    dark_time_us: int
    bitplanes: int
    VID: int
    PID: int
    trigger_out: TriggerOutConfig

    def __post_init__(self):
        if self.target_hz <= 0 or self.dark_time_us < 0 or not 0 < self.frame_utilization <= 1:
            raise ValueError('config.yaml DMD: need target_hz > 0, dark_time_us >= 0, 0 < frame_utilization <= 1')
        if self.exposure_us < self.min_exposure_us:
            raise ValueError(f'config.yaml DMD.exposure_us {self.exposure_us} is below min_exposure_us {self.min_exposure_us}')


@dataclass(frozen=True)
class Config:
    log_level: str
    Run: RunConfig
    Laser: LaserConfig
    Camera: CameraConfig
    DMD: DmdConfig


def _build(cls: Any, data: dict, where: str) -> Any:
    names = {f.name for f in fields(cls)}
    if unknown := sorted(set(data) - names):
        raise ValueError(f'config.yaml {where}: unknown key(s) {unknown}')
    values = {}
    for f in fields(cls):
        if f.name not in data:
            if f.default is MISSING:
                raise ValueError(f'config.yaml {where}: missing key {f.name!r}')
            continue
        values[f.name] = _build(f.type, data[f.name], f'{where}.{f.name}') if is_dataclass(f.type) else data[f.name]
    return cls(**values)


with open(CONFIG_PATH) as config_file:
    CONFIG: Config = _build(Config, yaml.safe_load(config_file), 'top level')
