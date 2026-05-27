"""Compatibility shim for dmdcontrol.hardware.flood."""

from __future__ import annotations

import sys

from dmdcontrol.hardware import flood as _flood
from dmdcontrol.hardware.flood import main


if __name__ == "__main__":
    raise SystemExit(main())

sys.modules[__name__] = _flood
