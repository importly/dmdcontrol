"""SIGTERM, SIGHUP and Ctrl-C raise Stopped, so every `with` unwinds: data.h5 closes and the rig is released."""

import signal
from collections.abc import Iterator
from contextlib import contextmanager

_deferring = False
_pending: int | None = None


class Stopped(BaseException):

    def __init__(self, signum: int):
        self.signum = signum
        super().__init__(signal.Signals(signum).name)


def _handler(signum: int, _frame) -> None:
    global _pending
    if _deferring:
        _pending = _pending or signum
        return
    raise Stopped(signum)


def install() -> None:
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, _handler)


@contextmanager
def deferred() -> Iterator[None]:
    """Hold a stop signal until the block ends."""
    global _deferring, _pending
    _deferring = True
    try:
        yield
    finally:
        _deferring = False
    if _pending is not None:
        signum, _pending = _pending, None
        raise Stopped(signum)
