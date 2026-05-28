"""Compatibility shim for dmdcontrol.support.constants."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.support import constants as _constants

sys.modules[__name__] = _constants
