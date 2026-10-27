"""Makes the OpenEB (Prophesee Metavision) build on the rig importable, plus open_camera().

Installed into the dmdcontrol venv by `uv sync` on Linux (see pyproject.toml). Import it before anything
from metavision:

    import evcam
    from metavision_core.event_io import EventsIterator

    device = evcam.open_camera()
    for evs in EventsIterator.from_device(device, delta_t=10_000):
        ...
"""
import contextlib
import os
import sys
from pathlib import Path

OPENEB = Path.home() / "openeb"
BUILD = OPENEB / "build-py314"  # made by prophesee/setup_openeb.sh
PYTHON = (3, 14)  # the compiled bindings in BUILD only load in this Python version

if sys.version_info[:2] != PYTHON:
    raise ImportError(f"OpenEB in {BUILD} is built for Python 3.14; this is {sys.version.split()[0]}")
if not (BUILD / "py3").is_dir():
    raise ImportError(f"no OpenEB build at {BUILD}; run prophesee/setup_openeb.sh on the rig")

sys.path[:0] = [str(BUILD / "py3"), str(OPENEB / "sdk/modules/core/python/pypkg")]
os.environ.setdefault("MV_HAL_PLUGIN_PATH", str(BUILD / "lib/metavision/hal/plugins"))
os.environ.setdefault("HDF5_PLUGIN_PATH", str(BUILD / "lib/hdf5/plugin"))

from metavision_core.event_io.raw_reader import initiate_device  # noqa: E402


@contextlib.contextmanager
def _quiet_stderr():
    # The HAL's legacy FX3 probe prints harmless LIBUSB_ERROR_PIPE / "FPGA is not properly configured"
    # lines from C++ on every camera open, so silence fd 2 while the device is being discovered.
    saved, devnull = os.dup(2), os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    try:
        yield
    finally:
        os.dup2(saved, 2)
        os.close(devnull)
        os.close(saved)


def open_camera(path=""):
    """Open the live camera (path="") or a .raw recording and return the HAL device."""
    try:
        with _quiet_stderr():
            device = initiate_device(path)
    except OSError:
        raise SystemExit(f"could not open {path or 'the camera'}: not plugged in, or another script is using it")
    if device.get_i_geometry() is None:
        raise SystemExit("board found but no sensor detected: unplug USB and DC, plug DC first, then USB")
    return device
