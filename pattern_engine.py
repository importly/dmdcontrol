"""Compatibility shim for dmdcontrol.patterns.engine."""

from __future__ import annotations

import sys

from dmdcontrol.patterns import engine as _engine

sys.modules[__name__] = _engine
