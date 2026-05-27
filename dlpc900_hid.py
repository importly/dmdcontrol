"""Compatibility shim for dmdcontrol.hardware.dlpc900."""

from __future__ import annotations

import sys

from dmdcontrol.hardware import dlpc900 as _dlpc900

sys.modules[__name__] = _dlpc900
