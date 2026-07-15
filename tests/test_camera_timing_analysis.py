import numpy as np
import pytest

from dmdcontrol.camera.timing_analysis import (
    recommend_polarity_window,
    score_polarity_windows,
    select_cycle_triggers,
)


def _burst(trigger_us, offset_us, *, positive, count=12):
    timestamps = trigger_us + offset_us + np.arange(count, dtype=np.int64) * 150
    polarities = np.full(count, positive, dtype=bool)
    return timestamps, polarities


def test_recommendation_skips_transient_first_cycle_and_finds_late_window():
    labels = ("1", "blank", "2", "blank")
    trigger_period_us = 20_000
    triggers = np.arange(8, dtype=np.int64) * trigger_period_us
    timestamp_parts = []
    polarity_parts = []

    for trigger, label in zip(triggers[:4], labels, strict=True):
        timestamps, polarities = _burst(
            trigger,
            2_000,
            positive=label != "blank",
        )
        timestamp_parts.append(timestamps)
        polarity_parts.append(polarities)
    for trigger, label in zip(triggers[4:], labels, strict=True):
        timestamps, polarities = _burst(
            trigger,
            12_000,
            positive=label != "blank",
        )
        timestamp_parts.append(timestamps)
        polarity_parts.append(polarities)

    recommendation = recommend_polarity_window(
        np.concatenate(timestamp_parts),
        np.concatenate(polarity_parts),
        triggers,
        labels,
        trigger_period_us=trigger_period_us,
        window_us=2_000,
        offset_step_us=1_000,
    )

    assert recommendation.available_full_cycles == 2
    assert recommendation.skipped_first_cycle is True
    assert recommendation.per_cycle_best[0].offset_us == 2_000
    assert recommendation.selected.cycle_index == 1
    assert recommendation.selected.offset_us == 12_000
    assert recommendation.selected.expected_events == 48
    assert recommendation.selected.unexpected_events == 0
    assert recommendation.selected.polarity_accuracy == 1.0


def test_polarity_score_counts_opposite_events_as_unexpected():
    labels = ("count:1", "blank")
    triggers = np.asarray([0, 20_000], dtype=np.int64)
    event_timestamps = np.asarray(
        [1_000, 1_100, 1_200, 21_000, 21_100, 21_200],
        dtype=np.int64,
    )
    event_polarities = np.asarray(
        [True, True, False, False, False, True],
        dtype=bool,
    )

    score = score_polarity_windows(
        event_timestamps,
        event_polarities,
        triggers,
        labels,
        cycle_index=0,
        offsets_us=[1_000],
        window_us=1_000,
    )[0]

    assert score.expected_events == 4
    assert score.unexpected_events == 2
    assert score.net_score == 2
    assert score.polarity_accuracy == pytest.approx(4 / 6)


def test_select_cycle_triggers_returns_only_complete_requested_cycles():
    triggers = np.arange(12, dtype=np.int64) * 100

    selected = select_cycle_triggers(
        triggers,
        cycle_length=4,
        cycle_index=1,
        cycles=2,
    )

    np.testing.assert_array_equal(selected, triggers[4:12])


def test_recommendation_rejects_unknown_semantic_labels():
    with pytest.raises(ValueError, match="count labels"):
        recommend_polarity_window(
            np.asarray([], dtype=np.int64),
            np.asarray([], dtype=bool),
            np.asarray([0], dtype=np.int64),
            ["mystery"],
            trigger_period_us=20_000,
        )
