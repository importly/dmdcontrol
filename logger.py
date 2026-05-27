"""Compatibility shim for dmdcontrol.support.logging."""

from __future__ import annotations

import sys

from dmdcontrol.support import logging as _logging

sys.modules[__name__] = _logging
