"""Compatibility shim for dmdcontrol.patterns.modes."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.patterns import modes as _modes

sys.modules[__name__] = _modes
