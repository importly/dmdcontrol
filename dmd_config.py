"""Compatibility shim for dmdcontrol.hardware.mapping."""

from __future__ import annotations

import sys

from dmdcontrol.hardware import mapping as _mapping
from dmdcontrol.hardware.mapping import main

if __name__ == "__main__":
    raise SystemExit(main())

sys.modules[__name__] = _mapping
