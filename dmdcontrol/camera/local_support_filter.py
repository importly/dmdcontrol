from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np

from dmdcontrol.support.constants import (
    DEFAULT_FILTER_DELTA_T_US,
    DEFAULT_FILTER_POLARITY,
    DEFAULT_FILTER_THRESHOLD,
    DEFAULT_FILTER_WINDOW_PX,
)

PolaritySupport = Literal["same", "any"]


@dataclass(frozen=True)
class LocalSupportFilterConfig:
    enabled: bool = False
    delta_t_us: int = DEFAULT_FILTER_DELTA_T_US
    window_px: int = DEFAULT_FILTER_WINDOW_PX
    threshold: int = DEFAULT_FILTER_THRESHOLD
    polarity: PolaritySupport = DEFAULT_FILTER_POLARITY

    def validate(self) -> None:
        if self.delta_t_us <= 0:
            raise ValueError("delta_t_us must be positive")
        if self.window_px < 1:
            raise ValueError("window_px must be >= 1")
        if self.window_px % 2 != 1:
            raise ValueError("window_px must be odd")
        if self.threshold < 0:
            raise ValueError("threshold must be >= 0")
        if self.polarity not in ("same", "any"):
            raise ValueError("polarity must be 'same' or 'any'")

    def to_metadata(self) -> dict:
        out = asdict(self)
        out["algorithm"] = "centered-local-support"
        out["note"] = (
            "Practical notebook-validated local support filter; "
            "not a source-faithful DV Runtime YNoise implementation.")
        return out


@dataclass(frozen=True)
class LocalSupportFilterStats:
    raw_events: int
    filtered_events: int
    kept_fraction: float
    raw_on: int
    raw_off: int
    filtered_on: int
    filtered_off: int

    def to_metadata(self) -> dict:
        return asdict(self)


def centered_local_support_mask(
    x: np.ndarray,
    y: np.ndarray,
    t: np.ndarray,
    p: np.ndarray,
    resolution: tuple[int,
                      int],
    config: LocalSupportFilterConfig,
) -> np.ndarray:
    """Return boolean keep mask for centered causal local-support event filtering.

    This is intentionally not the exact DV Runtime YNoise/Yang source behavior.
    It is the practical filter validated on the DVXplorer notebook run:
    delta_t_us=50000, window_px=3, threshold=2, polarity='same'.

    Events are evaluated before the current event updates the per-pixel memory.
    """
    config.validate()

    x = np.asarray(x)
    y = np.asarray(y)
    t = np.asarray(t)
    p = np.asarray(p).astype(np.bool_, copy=False)

    if not (len(x) == len(y) == len(t) == len(p)):
        raise ValueError("x, y, t, p must have the same length")

    width, height = map(int, resolution)
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid resolution: {resolution}")

    n = len(t)
    keep = np.zeros(n, dtype=np.bool_)

    if n == 0:
        return keep

    # Shape is [x, y] so indexing matches event coordinates directly.
    last_ts = np.full((width, height), -1, dtype=np.int64)
    last_pol = np.zeros((width, height), dtype=np.bool_)

    radius = config.window_px // 2
    delta_t = int(config.delta_t_us)
    threshold = int(config.threshold)
    require_same_polarity = config.polarity == "same"

    for i in range(n):
        xi = int(x[i])
        yi = int(y[i])

        if not (0 <= xi < width and 0 <= yi < height):
            continue

        ti = int(t[i])
        pi = bool(p[i])

        x0 = max(0, xi - radius)
        x1 = min(width, xi + radius + 1)
        y0 = max(0, yi - radius)
        y1 = min(height, yi + radius + 1)

        window_ts = last_ts[x0:x1, y0:y1]
        recent = (window_ts >= 0) & (window_ts > (ti - delta_t))

        if require_same_polarity:
            same = last_pol[x0:x1, y0:y1] == pi
            count = int(np.count_nonzero(recent & same))
        else:
            count = int(np.count_nonzero(recent))

        if count >= threshold:
            keep[i] = True

        # Causal update after keep/drop decision.
        last_ts[xi, yi] = ti
        last_pol[xi, yi] = pi

    return keep


def apply_local_support_filter_arrays(
    x: np.ndarray,
    y: np.ndarray,
    t: np.ndarray,
    p: np.ndarray,
    resolution: tuple[int,
                      int],
    config: LocalSupportFilterConfig,
) -> tuple[dict[str,
                np.ndarray],
           np.ndarray,
           LocalSupportFilterStats]:
    """Filter event arrays and return filtered arrays, mask, and stats."""
    config.validate()

    x = np.asarray(x)
    y = np.asarray(y)
    t = np.asarray(t)
    p = np.asarray(p).astype(np.bool_, copy=False)

    if not (len(x) == len(y) == len(t) == len(p)):
        raise ValueError("x, y, t, p must have the same length")

    if not config.enabled:
        mask = np.ones(len(t), dtype=np.bool_)
    else:
        mask = centered_local_support_mask(x, y, t, p, resolution, config)

    filtered = {
        "x": x[mask],
        "y": y[mask],
        "t": t[mask],
        "p": p[mask],
    }

    raw_on = int(np.count_nonzero(p))
    filtered_on = int(np.count_nonzero(filtered["p"]))
    stats = LocalSupportFilterStats(
        raw_events=int(len(t)),
        filtered_events=int(mask.sum()),
        kept_fraction=float(mask.mean()) if len(mask) else 0.0,
        raw_on=raw_on,
        raw_off=int(len(p) - raw_on),
        filtered_on=filtered_on,
        filtered_off=int(len(filtered["p"]) - filtered_on),
    )

    return filtered, mask, stats


def add_event_noise_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--event-noise-filter", default="none", choices=["none", "local-support"])
    parser.add_argument(
        "--event-filter-delta-us",
        type=_positive_int,
        default=DEFAULT_FILTER_DELTA_T_US)
    parser.add_argument(
        "--event-filter-window-px",
        type=_positive_int,
        default=DEFAULT_FILTER_WINDOW_PX)
    parser.add_argument(
        "--event-filter-threshold",
        type=_non_negative_int,
        default=DEFAULT_FILTER_THRESHOLD)
    parser.add_argument(
        "--event-filter-polarity",
        default=DEFAULT_FILTER_POLARITY,
        choices=["same",
                 "any"])
    parser.add_argument("--save-filtered-events", action="store_true", default=False)


def event_noise_filter_config_from_args(args: argparse.Namespace) -> LocalSupportFilterConfig:
    config = LocalSupportFilterConfig(
        enabled=args.event_noise_filter == "local-support",
        delta_t_us=args.event_filter_delta_us,
        window_px=args.event_filter_window_px,
        threshold=args.event_filter_threshold,
        polarity=args.event_filter_polarity,
    )
    config.validate()
    return config


def event_noise_filter_metadata(
    config: LocalSupportFilterConfig,
    stats: LocalSupportFilterStats | None = None,
) -> dict:
    metadata = config.to_metadata()
    if not config.enabled:
        metadata["algorithm"] = "none"
        metadata["note"] = (
            "Event noise filtering disabled. Local-support parameters are resolved "
            "but were not applied.")
    if stats is not None:
        metadata.update(stats.to_metadata())
    return metadata


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be positive") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _non_negative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be >= 0") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("value must be >= 0")
    return number
