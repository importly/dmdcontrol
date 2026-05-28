"""Compatibility shim for dmdcontrol.patterns.paired."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.patterns import paired as _paired

sys.modules[__name__] = _paired
