"""Compatibility shim for dmdcontrol.support.logging."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.support import logging as _logging

sys.modules[__name__] = _logging
