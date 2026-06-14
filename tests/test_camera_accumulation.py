import numpy as np

from dmdcontrol.camera.accumulation import (
    EventRecord,
    TriggerRecord,
    accumulate_events_for_triggers,
    filter_rising_triggers,
)


def test_filter_rising_triggers_keeps_rising_only():
    triggers = [
        TriggerRecord(timestamp=10,
                      edge="rising"),
        TriggerRecord(timestamp=20,
                      edge="falling"),
        TriggerRecord(timestamp=30,
                      edge="rising"),
    ]

    assert [t.timestamp for t in filter_rising_triggers(triggers)] == [10, 30]


def test_filter_rising_triggers_understands_dv_trigger_type():

    class Trigger:

        def __init__(self, timestamp, trigger_type):
            self._timestamp = timestamp
            self._trigger_type = trigger_type

        def timestamp(self):
            return self._timestamp

        def type(self):
            return self._trigger_type

    triggers = [
        Trigger(10,
                "TriggerType.EXTERNAL_SIGNAL_RISING_EDGE"),
        Trigger(20,
                "TriggerType.EXTERNAL_SIGNAL_FALLING_EDGE"),
    ]

    assert [trigger.timestamp() for trigger in filter_rising_triggers(triggers)] == [10]


def test_linear_accumulation_counts_positive_events_by_trigger_window():
    triggers = [
        TriggerRecord(timestamp=100,
                      edge="rising"),
        TriggerRecord(timestamp=200,
                      edge="rising"),
    ]
    events = [
        EventRecord(timestamp=105,
                    x=1,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=110,
                    x=1,
                    y=2,
                    polarity=True),
        EventRecord(timestamp=115,
                    x=3,
                    y=4,
                    polarity=False),
        EventRecord(timestamp=205,
                    x=0,
                    y=0,
                    polarity=True),
    ]

    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(5,
                    6),
        window_us=50,
        polarity_mode="positive",
    )

    assert frames.shape == (2, 6, 5)
    assert frames.dtype == np.float32
    assert frames[0, 2, 1] == 2
    assert frames[0, 4, 3] == 0
    assert frames[1, 0, 0] == 1


def test_linear_accumulation_supports_signed_and_ignore_modes():
    triggers = [TriggerRecord(timestamp=100, edge="rising")]
    events = [
        EventRecord(timestamp=100,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=101,
                    x=1,
                    y=1,
                    polarity=False),
        EventRecord(timestamp=102,
                    x=1,
                    y=1,
                    polarity=False),
    ]

    signed = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=10,
        polarity_mode="signed",
    )
    ignored = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=10,
        polarity_mode="ignore",
    )

    assert signed[0, 1, 1] == -1
    assert ignored[0, 1, 1] == 3


def test_window_boundary_left_inclusive():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [EventRecord(timestamp=1000, x=1, y=1, polarity=True)]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 1.0


def test_window_boundary_right_exclusive():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [EventRecord(timestamp=1100, x=1, y=1, polarity=True)]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 0.0


def test_window_boundary_one_tick_inside():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [EventRecord(timestamp=1099, x=1, y=1, polarity=True)]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 1.0


def test_window_boundary_one_tick_before_start():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [EventRecord(timestamp=999, x=1, y=1, polarity=True)]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 0.0


def test_accumulation_window_can_start_after_trigger():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [
        EventRecord(timestamp=1005,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1025,
                    x=2,
                    y=1,
                    polarity=True),
    ]

    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=20,
        polarity_mode="positive",
        window_start_offset_us=20,
    )

    assert frames[0, 1, 1] == 0.0
    assert frames[0, 1, 2] == 1.0


def test_events_between_triggers_are_discarded():
    triggers = [
        TriggerRecord(timestamp=1000,
                      edge="rising"),
        TriggerRecord(timestamp=2000,
                      edge="rising"),
    ]
    events = [
        EventRecord(timestamp=1200,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1500,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1900,
                    x=1,
                    y=1,
                    polarity=True),
    ]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 0.0
    assert frames[1, 1, 1] == 0.0


def test_polarity_positive_ignores_negative_events():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [
        EventRecord(timestamp=1010,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1020,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1030,
                    x=1,
                    y=1,
                    polarity=False),
    ]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 2.0


def test_polarity_signed_subtracts_negative_events():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events_1 = [
        EventRecord(timestamp=1010,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1020,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1030,
                    x=1,
                    y=1,
                    polarity=False),
    ]
    frames_1 = accumulate_events_for_triggers(
        events_1,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="signed")
    assert frames_1[0, 1, 1] == 1.0

    events_2 = [
        EventRecord(timestamp=1010,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1020,
                    x=1,
                    y=1,
                    polarity=False),
        EventRecord(timestamp=1030,
                    x=1,
                    y=1,
                    polarity=False),
    ]
    frames_2 = accumulate_events_for_triggers(
        events_2,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="signed")
    assert frames_2[0, 1, 1] == -1.0


def test_polarity_ignore_counts_all_events_equally():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [
        EventRecord(timestamp=1010,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1020,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1030,
                    x=1,
                    y=1,
                    polarity=False),
    ]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="ignore")
    assert frames[0, 1, 1] == 3.0


def test_out_of_bounds_events_are_silently_discarded():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [
        EventRecord(timestamp=1010,
                    x=10,
                    y=5,
                    polarity=True),
        EventRecord(timestamp=1020,
                    x=-1,
                    y=5,
                    polarity=True),
        EventRecord(timestamp=1030,
                    x=5,
                    y=10,
                    polarity=True),
        EventRecord(timestamp=1040,
                    x=5,
                    y=-1,
                    polarity=True),
        EventRecord(timestamp=1050,
                    x=5,
                    y=5,
                    polarity=True),
    ]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(10,
                    10),
        window_us=100,
        polarity_mode="positive")
    assert frames.shape == (1, 10, 10)
    assert np.sum(frames) == 1.0
    assert frames[0, 5, 5] == 1.0


def test_empty_events_returns_zero_frames():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    frames = accumulate_events_for_triggers(
        [],
        triggers,
        resolution=(5,
                    5),
        window_us=100,
        polarity_mode="positive")
    assert frames.shape == (1, 5, 5)
    assert np.sum(frames) == 0.0


def test_accumulation_supports_native_numpy_structured_arrays():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events_arr = np.array(
        [(1000,
          1,
          1,
          True),
         (1050,
          1,
          1,
          False)],
        dtype=[("timestamp",
                np.int64),
               ("x",
                np.int16),
               ("y",
                np.int16),
               ("polarity",
                np.bool_)])
    frames = accumulate_events_for_triggers(
        [events_arr],
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 1.0


def test_accumulation_supports_direct_numpy_structured_array():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events_arr = np.array(
        [(1000,
          1,
          1,
          True),
         (1050,
          1,
          1,
          False)],
        dtype=[("timestamp",
                np.int64),
               ("x",
                np.int16),
               ("y",
                np.int16),
               ("polarity",
                np.bool_)])

    frames = accumulate_events_for_triggers(
        events_arr,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")

    assert frames[0, 1, 1] == 1.0


def test_accumulation_supports_numpy_t_and_p_fields():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events_arr = np.array(
        [(1000,
          1,
          1,
          True),
         (1050,
          1,
          1,
          False)],
        dtype=[("t",
                np.int64),
               ("x",
                np.int16),
               ("y",
                np.int16),
               ("p",
                np.bool_)])

    frames = accumulate_events_for_triggers(
        [events_arr],
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="signed")

    assert frames[0, 1, 1] == 0.0


def test_accumulation_preserves_large_record_coordinates():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    events = [EventRecord(timestamp=1000, x=40000, y=2, polarity=True)]

    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(40001,
                    3),
        window_us=100,
        polarity_mode="positive")

    assert frames[0, 2, 40000] == 1.0


def test_accumulation_sorts_unsorted_events_correctly():
    triggers = [TriggerRecord(timestamp=1000, edge="rising")]
    # Insert out of order
    events = [
        EventRecord(timestamp=1050,
                    x=1,
                    y=1,
                    polarity=True),
        EventRecord(timestamp=1010,
                    x=1,
                    y=1,
                    polarity=True),
    ]
    frames = accumulate_events_for_triggers(
        events,
        triggers,
        resolution=(3,
                    3),
        window_us=100,
        polarity_mode="positive")
    assert frames[0, 1, 1] == 2.0
