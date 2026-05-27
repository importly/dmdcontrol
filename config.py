"""Compatibility shim for dmdcontrol.support.constants."""

from __future__ import annotations

import sys

from dmdcontrol.support import constants as _constants

sys.modules[__name__] = _constants
