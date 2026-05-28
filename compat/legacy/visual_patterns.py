"""Compatibility shim for dmdcontrol.patterns.visual."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.patterns import visual as _visual

sys.modules[__name__] = _visual
