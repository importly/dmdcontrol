"""Compatibility shim for dmdcontrol.preview.render."""

from __future__ import annotations

import sys

from dmdcontrol.preview import render as _render

sys.modules[__name__] = _render
