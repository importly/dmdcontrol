import numpy as np
import pytest

from dmdcontrol.camera.local_support_filter import (
    LocalSupportFilterConfig,
    apply_local_support_filter_arrays,
    centered_local_support_mask,
)


def test_config_validate_accepts_default_values():
    LocalSupportFilterConfig().validate()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"delta_t_us": 0}, "delta_t_us must be positive"),
        ({"window_px": 0}, "window_px must be >= 1"),
        ({"window_px": 2}, "window_px must be odd"),
        ({"threshold": -1}, "threshold must be >= 0"),
        ({"polarity": "bad"}, "polarity must be 'same' or 'any'"),
    ],
)
def test_config_validate_rejects_invalid_values(kwargs, message):
    config = LocalSupportFilterConfig(**kwargs)

    with pytest.raises(ValueError, match=message):
        config.validate()


def test_config_metadata_names_practical_local_support_not_y_noise():
    metadata = LocalSupportFilterConfig(enabled=True).to_metadata()

    assert metadata["algorithm"] == "centered-local-support"
    assert "not a source-faithful DV Runtime YNoise" in metadata["note"]


def test_isolated_single_event_drops_when_enabled():
    mask = centered_local_support_mask(
        x=np.array([1]),
        y=np.array([1]),
        t=np.array([100]),
        p=np.array([True]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(
            enabled=True,
            delta_t_us=50,
            window_px=3,
            threshold=1,
            polarity="same",
        ),
    )

    assert mask.tolist() == [False]


def test_nearby_same_polarity_events_can_pass_thresholds():
    x = np.array([1, 1, 2])
    y = np.array([1, 2, 1])
    t = np.array([100, 110, 120])
    p = np.array([True, True, True])

    threshold_one = centered_local_support_mask(
        x,
        y,
        t,
        p,
        resolution=(4, 4),
        config=LocalSupportFilterConfig(enabled=True, delta_t_us=50, window_px=3, threshold=1),
    )
    threshold_two = centered_local_support_mask(
        x,
        y,
        t,
        p,
        resolution=(4, 4),
        config=LocalSupportFilterConfig(enabled=True, delta_t_us=50, window_px=3, threshold=2),
    )

    assert threshold_one.tolist() == [False, True, True]
    assert threshold_two.tolist() == [False, False, True]


def test_event_outside_delta_window_does_not_support():
    mask = centered_local_support_mask(
        x=np.array([1, 1]),
        y=np.array([1, 2]),
        t=np.array([100, 200]),
        p=np.array([True, True]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(enabled=True, delta_t_us=50, window_px=3, threshold=1),
    )

    assert mask.tolist() == [False, False]


def test_opposite_polarity_does_not_support_when_same_required():
    mask = centered_local_support_mask(
        x=np.array([1, 1]),
        y=np.array([1, 2]),
        t=np.array([100, 110]),
        p=np.array([True, False]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(
            enabled=True,
            delta_t_us=50,
            window_px=3,
            threshold=1,
            polarity="same",
        ),
    )

    assert mask.tolist() == [False, False]


def test_opposite_polarity_supports_when_any_polarity_allowed():
    mask = centered_local_support_mask(
        x=np.array([1, 1]),
        y=np.array([1, 2]),
        t=np.array([100, 110]),
        p=np.array([True, False]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(
            enabled=True,
            delta_t_us=50,
            window_px=3,
            threshold=1,
            polarity="any",
        ),
    )

    assert mask.tolist() == [False, True]


def test_current_event_does_not_support_itself():
    mask = centered_local_support_mask(
        x=np.array([1]),
        y=np.array([1]),
        t=np.array([100]),
        p=np.array([True]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(enabled=True, delta_t_us=50, window_px=1, threshold=1),
    )

    assert mask.tolist() == [False]


def test_invalid_coordinates_do_not_crash_or_update_support_memory():
    mask = centered_local_support_mask(
        x=np.array([9, 1, 1]),
        y=np.array([9, 1, 2]),
        t=np.array([100, 110, 120]),
        p=np.array([True, True, True]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(enabled=True, delta_t_us=50, window_px=3, threshold=1),
    )

    assert mask.tolist() == [False, False, True]


def test_disabled_filter_preserves_arrays_and_reports_stats():
    filtered, mask, stats = apply_local_support_filter_arrays(
        x=np.array([1, 2]),
        y=np.array([1, 2]),
        t=np.array([100, 110]),
        p=np.array([True, False]),
        resolution=(4, 4),
        config=LocalSupportFilterConfig(enabled=False),
    )

    assert mask.tolist() == [True, True]
    assert filtered["x"].tolist() == [1, 2]
    assert filtered["p"].tolist() == [True, False]
    assert stats.to_metadata() == {
        "raw_events": 2,
        "filtered_events": 2,
        "kept_fraction": 1.0,
        "raw_on": 1,
        "raw_off": 1,
        "filtered_on": 1,
        "filtered_off": 1,
    }
