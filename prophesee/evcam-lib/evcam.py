"""Camera helpers for the OpenEB (Prophesee Metavision) build on the rig."""
import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path

OPENEB = Path.home() / "openeb"
BUILD = OPENEB / "build-py314"
PYTHON = (3, 14)

if sys.version_info[:2] != PYTHON:
    raise ImportError(f"OpenEB in {BUILD} is built for Python 3.14; this is {sys.version.split()[0]}")
if not (BUILD / "py3").is_dir():
    raise ImportError(f"no OpenEB build at {BUILD}; run prophesee/setup_openeb.sh on the rig")

_paths = (str(BUILD / "py3"), str(OPENEB / "sdk/modules/core/python/pypkg"))
sys.path += [p for p in _paths if p not in sys.path]
os.environ.setdefault("MV_HAL_PLUGIN_PATH", str(BUILD / "lib/metavision/hal/plugins"))
os.environ.setdefault("HDF5_PLUGIN_PATH", str(BUILD / "lib/hdf5/plugin"))

from metavision_core.event_io.raw_reader import initiate_device  # noqa: E402
from metavision_hal import Device  # noqa: E402


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


def open_camera(path: str = "") -> Device:
    """Open the live camera (path="") or a .raw recording."""
    try:
        with quiet_stderr():
            device = initiate_device(path)
    except OSError:
        raise SystemExit(f"could not open {path or 'the camera'}: unplugged, or in use by another process")
    if device.get_i_geometry() is None:
        raise SystemExit("board found but no sensor detected: unplug USB and DC, plug DC first, then USB")
    return device
