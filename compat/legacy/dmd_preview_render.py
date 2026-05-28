"""Compatibility shim for dmdcontrol.preview.render."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.preview import render as _render

sys.modules[__name__] = _render
