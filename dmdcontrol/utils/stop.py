"""Stop a run cleanly on SIGTERM, SIGHUP or Ctrl-C.

Python's default for SIGTERM (kill, a shutdown) and SIGHUP (the ssh session closing outside
screen) ends the process at once: no `with` block exits, so data.h5 is never closed and the DMDs,
camera and laser are not released. install() turns those signals, and Ctrl-C, into a Stopped
exception in the main thread, so everything unwinds the way it does for any other error.

Inside a deferred() block (collect.py writing a pass) a signal waits until the block ends, so a
pass is always written whole and every column of data.h5 keeps the same number of rows.

kill -9 and power cuts cannot be caught; for those collect.py flushes data.h5 after every pass.
"""

from __future__ import annotations

import signal
from collections.abc import Iterator
from contextlib import contextmanager

SIGNALS = ('SIGTERM', 'SIGHUP', 'SIGINT')

_deferring = False
_pending: int | None = None


class Stopped(BaseException):
    """A stop signal, raised in the main thread. A BaseException, so `except Exception` lets it through."""

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
    """Route the stop signals to Stopped. Call once, from the main thread."""
    for name in SIGNALS:
        if hasattr(signal, name):  # Windows has no SIGHUP
            signal.signal(getattr(signal, name), _handler)


@contextmanager
def deferred() -> Iterator[None]:
    """A stop signal that arrives inside the block is raised as Stopped when the block ends."""
    global _deferring, _pending
    _deferring = True
    try:
        yield
    finally:
        _deferring = False
    if _pending is not None:
        signum, _pending = _pending, None
        raise Stopped(signum)
