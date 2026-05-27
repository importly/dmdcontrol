"""Compatibility shim for dmdcontrol.patterns.kernel."""

from __future__ import annotations

import sys

from dmdcontrol.patterns import kernel as _kernel

sys.modules[__name__] = _kernel
