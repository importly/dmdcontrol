"""Compatibility shim for dmdcontrol.runtime.loop."""

from __future__ import annotations

import sys

from dmdcontrol.runtime import loop as _loop

sys.modules[__name__] = _loop
