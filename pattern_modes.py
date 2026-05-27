"""Compatibility shim for dmdcontrol.patterns.modes."""

from __future__ import annotations

import sys

from dmdcontrol.patterns import modes as _modes

sys.modules[__name__] = _modes
