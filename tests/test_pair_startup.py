import logging
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from dmdcontrol.runtime import pair
from dmdcontrol.support.logging import logger


def timing():
    return {
        "sequence_utilization": 1.0,
        "trig2_mode": "per_bitplane",
        "exposure_us": 1000,
        "dark_us": 0,
    }


def test_prepare_pair_controllers_runs_both_usb_setups_concurrently(
    monkeypatch,
    caplog,
):
    entered = set()
    entered_lock = Lock()
    both_entered = Event()
    dlpc_a = SimpleNamespace(name="A")
    dlpc_b = SimpleNamespace(name="B")
    caplog.set_level(logging.INFO, logger="dmdcontrol")

    def fake_prepare(dlpc, *_args, **_kwargs):
        with entered_lock:
            entered.add(dlpc.name)
            if entered == {"A", "B"}:
                both_entered.set()
        assert both_entered.wait(timeout=1.0)
        logger.info(f"Nested setup for {dlpc.name}")
        return {"entries": [], "timing": {}}

    monkeypatch.setattr(pair, "prepare_dlpc900_for_video_pattern", fake_prepare)
    args = SimpleNamespace(dual_pixel=False, trigger_out_2_rising_delay_us=0)
    pair_config = SimpleNamespace(target_hz=60)

    pair._prepare_pair_controllers(
        dlpc_a,
        dlpc_b,
        args=args,
        pair_config=pair_config,
        timing_a=timing(),
        timing_b=timing(),
        entries_count_a=1,
        entries_count_b=1,
    )

    assert entered == {"A", "B"}
    messages = [record.getMessage() for record in caplog.records]
    assert "[DMD A] Nested setup for A" in messages
    assert "[DMD B] Nested setup for B" in messages
    assert "[DMD A] [+] Preparing controller without starting sequencer..." in messages
    assert "[DMD B] [+] Preparing controller without starting sequencer..." in messages
    assert "[DMD A] [+] Controller preparation complete." in messages
    assert "[DMD B] [+] Controller preparation complete." in messages


def test_prepare_pair_controllers_propagates_worker_failure(monkeypatch):
    def fake_prepare(dlpc, *_args, **_kwargs):
        if dlpc.name == "B":
            raise RuntimeError("B prepare failed")
        return {"entries": [], "timing": {}}

    monkeypatch.setattr(pair, "prepare_dlpc900_for_video_pattern", fake_prepare)
    args = SimpleNamespace(dual_pixel=False, trigger_out_2_rising_delay_us=0)
    pair_config = SimpleNamespace(target_hz=60)

    with pytest.raises(RuntimeError, match="B prepare failed"):
        pair._prepare_pair_controllers(
            SimpleNamespace(name="A"),
            SimpleNamespace(name="B"),
            args=args,
            pair_config=pair_config,
            timing_a=timing(),
            timing_b=timing(),
            entries_count_a=1,
            entries_count_b=1,
        )
