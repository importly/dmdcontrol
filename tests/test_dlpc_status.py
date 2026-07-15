from dmdcontrol.runtime import dlpc_status


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeDLPC900:
    def __init__(self, statuses, mode=2):
        self.statuses = list(statuses)
        self.mode = mode
        self.reads = 0

    def get_main_status(self):
        index = min(self.reads, len(self.statuses) - 1)
        self.reads += 1
        return self.statuses[index]

    def get_display_mode(self):
        return self.mode, None


def ready_status():
    return {
        "external_source_locked": True,
        "port1_syncs_valid": True,
        "video_frozen": False,
    }


def test_stable_external_lock_returns_early_after_continuous_ready_interval(monkeypatch):
    clock = FakeClock()
    dlpc = FakeDLPC900([ready_status()])
    monkeypatch.setattr(dlpc_status.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(dlpc_status.time, "sleep", clock.sleep)

    assert dlpc_status.wait_for_stable_external_lock(
        dlpc,
        timeout_s=3.0,
        stable_for_s=0.25,
        poll_interval_s=0.05,
        required_mode=2,
    )
    assert 0.25 <= clock.now < 0.5


def test_stable_external_lock_resets_after_an_unhealthy_sample(monkeypatch):
    clock = FakeClock()
    unlocked = {**ready_status(), "external_source_locked": False}
    dlpc = FakeDLPC900([ready_status(), ready_status(), unlocked, ready_status()])
    monkeypatch.setattr(dlpc_status.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(dlpc_status.time, "sleep", clock.sleep)

    assert dlpc_status.wait_for_stable_external_lock(
        dlpc,
        timeout_s=1.0,
        stable_for_s=0.2,
        poll_interval_s=0.05,
        required_mode=2,
    )
    assert clock.now >= 0.3


def test_stable_external_lock_uses_bounded_timeout(monkeypatch):
    clock = FakeClock()
    invalid_sync = {**ready_status(), "port1_syncs_valid": False}
    dlpc = FakeDLPC900([invalid_sync])
    monkeypatch.setattr(dlpc_status.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(dlpc_status.time, "sleep", clock.sleep)

    assert not dlpc_status.wait_for_stable_external_lock(
        dlpc,
        timeout_s=1.0,
        stable_for_s=0.2,
        poll_interval_s=0.1,
        required_mode=2,
    )
    assert clock.now == 1.0
