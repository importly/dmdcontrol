"""Compatibility shim for dmdcontrol.patterns.paired."""

from __future__ import annotations

import sys

from dmdcontrol.patterns import paired as _paired

sys.modules[__name__] = _paired
