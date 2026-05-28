"""Compatibility shim for dmdcontrol.hardware.flood."""

from __future__ import annotations

import sys

from _bootstrap import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dmdcontrol.hardware import flood as _flood
from dmdcontrol.hardware.flood import main

if __name__ == "__main__":
    raise SystemExit(main())

sys.modules[__name__] = _flood
