"""Compatibility shim for dmdcontrol.hardware.dlpc900."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.hardware import dlpc900 as _dlpc900

sys.modules[__name__] = _dlpc900
