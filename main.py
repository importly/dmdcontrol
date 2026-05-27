"""Compatibility entrypoint for the single-DMD runtime."""

from __future__ import annotations

import sys

from dmdcontrol.runtime import single as _single
from dmdcontrol.runtime.single import main


if __name__ == "__main__":
    raise SystemExit(main())

sys.modules[__name__] = _single
