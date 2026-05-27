"""Compatibility shim for dmdcontrol.runtime.lifecycle."""

from __future__ import annotations

import sys

from dmdcontrol.runtime import lifecycle as _lifecycle

sys.modules[__name__] = _lifecycle
