"""Compatibility shim for dmdcontrol.patterns.calibration_square."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.patterns import calibration_square as _calibration_square

sys.modules[__name__] = _calibration_square
