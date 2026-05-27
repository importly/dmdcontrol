"""Compatibility shim for dmdcontrol.patterns.visual."""

from __future__ import annotations

import sys

from dmdcontrol.patterns import visual as _visual

sys.modules[__name__] = _visual
