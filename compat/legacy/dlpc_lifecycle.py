"""Compatibility shim for dmdcontrol.runtime.lifecycle."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.runtime import lifecycle as _lifecycle

sys.modules[__name__] = _lifecycle
