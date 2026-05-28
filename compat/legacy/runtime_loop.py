"""Compatibility shim for dmdcontrol.runtime.loop."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.runtime import loop as _loop

sys.modules[__name__] = _loop
