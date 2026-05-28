"""Compatibility shim for dmdcontrol.hardware.wake."""

from __future__ import annotations

import sys

from dmdcontrol.hardware import wake as _wake
from dmdcontrol.hardware.wake import main

if __name__ == "__main__":
    raise SystemExit(main())

sys.modules[__name__] = _wake
