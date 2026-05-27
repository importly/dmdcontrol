"""Compatibility entrypoint for the paired dual-DMD runtime."""

from __future__ import annotations

import sys

from dmdcontrol.runtime import pair as _pair
from dmdcontrol.runtime.pair import main
from dmdcontrol.support.logging import logger


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception(f"[ERROR] {exc}")
        raise SystemExit(1)

sys.modules[__name__] = _pair
