"""Cycle-aware event-polarity timing analysis for triggered DMD captures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class PolarityWindowScore:
    """Polarity separation measured for one cycle and trigger-relative window."""

    cycle_index: int
    offset_us: int
    window_us: int
    expected_events: int
    unexpected_events: int
    net_score: int
    polarity_accuracy: float
    separation_ratio: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class TimingRecommendation:
    """Best stable cycle/window plus the best score observed in every cycle."""

    available_full_cycles: int
    selected: PolarityWindowScore
    per_cycle_best: tuple[PolarityWindowScore, ...]
    evaluated_offsets_us: tuple[int, ...]
    skipped_first_cycle: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "available_full_cycles": self.available_full_cycles,
            "selected": self.selected.to_dict(),
            "per_cycle_best": [score.to_dict() for score in self.per_cycle_best],
            "evaluated_offsets_us": list(self.evaluated_offsets_us),
            "skipped_first_cycle": self.skipped_first_cycle,
        }


def _semantic_expected_positive(labels: Sequence[str]) -> np.ndarray:
    expected_positive: list[bool] = []
    for raw_label in labels:
        label = str(raw_label).strip().lower()
        if label == "blank":
            expected_positive.append(False)
        elif label.startswith("count:") or label.isdigit():
            expected_positive.append(True)
        else:
            raise ValueError(
                "labels must contain count labels (for example 'count:1' or '1') "
                f"and optional 'blank' labels; got {raw_label!r}"
            )
    if not expected_positive:
        raise ValueError("labels must not be empty")
    return np.asarray(expected_positive, dtype=bool)


def _normalized_events(
    event_timestamps: np.ndarray,
    event_polarities: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    timestamps = np.asarray(event_timestamps, dtype=np.int64).reshape(-1)
    raw_polarities = np.asarray(event_polarities).reshape(-1)
    if timestamps.size != raw_polarities.size:
        raise ValueError(
            "event_timestamps and event_polarities must have equal lengths"
        )

    if raw_polarities.dtype == np.bool_:
        positive = raw_polarities.astype(bool, copy=False)
    else:
        positive = raw_polarities.astype(np.int64, copy=False) > 0

    if timestamps.size > 1 and np.any(np.diff(timestamps) < 0):
        order = np.argsort(timestamps, kind="stable")
        timestamps = timestamps[order]
        positive = positive[order]
    return timestamps, positive


def select_cycle_triggers(
    trigger_timestamps: np.ndarray,
    *,
    cycle_length: int,
    cycle_index: int,
    cycles: int = 1,
) -> np.ndarray:
    """Return complete semantic trigger cycles using a zero-based cycle index."""

    triggers = np.asarray(trigger_timestamps, dtype=np.int64).reshape(-1)
    if cycle_length <= 0:
        raise ValueError("cycle_length must be positive")
    if cycle_index < 0:
        raise ValueError("cycle_index must be non-negative")
    if cycles <= 0:
        raise ValueError("cycles must be positive")

    start = cycle_index * cycle_length
    stop = start + cycles * cycle_length
    if stop > triggers.size:
        raise ValueError(
            f"requested trigger cycles need {stop} triggers but only {triggers.size} are available"
        )
    return triggers[start:stop]


def score_polarity_windows(
    event_timestamps: np.ndarray,
    event_polarities: np.ndarray,
    trigger_timestamps: np.ndarray,
    labels: Sequence[str],
    *,
    cycle_index: int,
    offsets_us: Sequence[int],
    window_us: int,
) -> tuple[PolarityWindowScore, ...]:
    """Score candidate windows using positive=count and negative=blank polarity."""

    if window_us <= 0:
        raise ValueError("window_us must be positive")
    offsets = tuple(int(offset) for offset in offsets_us)
    if not offsets:
        raise ValueError("offsets_us must not be empty")

    expected_positive = _semantic_expected_positive(labels)
    cycle_triggers = select_cycle_triggers(
        trigger_timestamps,
        cycle_length=len(expected_positive),
        cycle_index=cycle_index,
    )
    timestamps, positive = _normalized_events(event_timestamps, event_polarities)
    positive_prefix = np.concatenate(
        (np.zeros(1, dtype=np.int64), np.cumsum(positive, dtype=np.int64))
    )

    scores: list[PolarityWindowScore] = []
    for offset_us in offsets:
        starts = cycle_triggers + offset_us
        stops = starts + int(window_us)
        left = np.searchsorted(timestamps, starts, side="left")
        right = np.searchsorted(timestamps, stops, side="left")
        positive_counts = positive_prefix[right] - positive_prefix[left]
        total_counts = right - left
        negative_counts = total_counts - positive_counts

        expected_events = int(
            positive_counts[expected_positive].sum()
            + negative_counts[~expected_positive].sum()
        )
        unexpected_events = int(
            negative_counts[expected_positive].sum()
            + positive_counts[~expected_positive].sum()
        )
        classified_events = expected_events + unexpected_events
        scores.append(
            PolarityWindowScore(
                cycle_index=int(cycle_index),
                offset_us=offset_us,
                window_us=int(window_us),
                expected_events=expected_events,
                unexpected_events=unexpected_events,
                net_score=expected_events - unexpected_events,
                polarity_accuracy=(
                    expected_events / classified_events if classified_events else 0.0
                ),
                separation_ratio=expected_events / (unexpected_events + 1.0),
            )
        )
    return tuple(scores)


def _score_rank(score: PolarityWindowScore) -> tuple[float, int, int, int, int]:
    return (
        score.polarity_accuracy,
        score.net_score,
        score.expected_events,
        -score.cycle_index,
        -score.offset_us,
    )


def recommend_polarity_window(
    event_timestamps: np.ndarray,
    event_polarities: np.ndarray,
    trigger_timestamps: np.ndarray,
    labels: Sequence[str],
    *,
    trigger_period_us: int,
    window_us: int = 4000,
    offset_step_us: int = 250,
    skip_first_cycle_when_possible: bool = True,
) -> TimingRecommendation:
    """Recommend a stable cycle and a window contained within one trigger period."""

    if trigger_period_us <= 0:
        raise ValueError("trigger_period_us must be positive")
    if window_us <= 0 or window_us > trigger_period_us:
        raise ValueError("window_us must be in the interval (0, trigger_period_us]")
    if offset_step_us <= 0:
        raise ValueError("offset_step_us must be positive")

    expected_positive = _semantic_expected_positive(labels)
    triggers = np.asarray(trigger_timestamps, dtype=np.int64).reshape(-1)
    available_full_cycles = int(triggers.size // expected_positive.size)
    if available_full_cycles < 1:
        raise ValueError(
            f"need {expected_positive.size} triggers for one cycle; got {triggers.size}"
        )

    latest_offset = int(trigger_period_us - window_us)
    offsets = list(range(0, latest_offset + 1, offset_step_us))
    if offsets[-1] != latest_offset:
        offsets.append(latest_offset)
    offsets_tuple = tuple(offsets)

    per_cycle_best: list[PolarityWindowScore] = []
    for cycle_index in range(available_full_cycles):
        scores = score_polarity_windows(
            event_timestamps,
            event_polarities,
            triggers,
            labels,
            cycle_index=cycle_index,
            offsets_us=offsets_tuple,
            window_us=window_us,
        )
        per_cycle_best.append(max(scores, key=_score_rank))

    skip_first = bool(skip_first_cycle_when_possible and available_full_cycles > 1)
    eligible = per_cycle_best[1:] if skip_first else per_cycle_best
    selected = max(eligible, key=_score_rank)
    return TimingRecommendation(
        available_full_cycles=available_full_cycles,
        selected=selected,
        per_cycle_best=tuple(per_cycle_best),
        evaluated_offsets_us=offsets_tuple,
        skipped_first_cycle=skip_first,
    )
