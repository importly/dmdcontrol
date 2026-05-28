"""Compatibility shim for dmdcontrol.patterns.engine."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.patterns import engine as _engine

sys.modules[__name__] = _engine
