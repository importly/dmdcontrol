"""Compatibility shim for dmdcontrol.patterns.kernel."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.patterns import kernel as _kernel

sys.modules[__name__] = _kernel
