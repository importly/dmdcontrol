"""Camera helpers for the OpenEB (Prophesee Metavision)"""
import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

BUILD = Path.home() / "openeb" / "build-py314"

if sys.version_info[:2] != (3, 14):
    raise ImportError(f"OpenEB in {BUILD} is built for Python 3.14; this is {sys.version.split()[0]}")
if not (BUILD / "py3").is_dir():
    raise ImportError(f"no OpenEB build at {BUILD}; run prophesee/setup_openeb.sh on the rig")


@contextlib.contextmanager
def quiet_stderr() -> Iterator[None]:
    """Silence C++ stderr, e.g. the harmless LIBUSB_ERROR_PIPE lines printed while a camera is found."""
    saved, devnull = os.dup(2), os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(devnull)
        os.close(saved)
