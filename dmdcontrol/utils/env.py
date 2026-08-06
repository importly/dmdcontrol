"""Gets parent level path."""

from pathlib import Path

WORKSPACE = Path(__file__).parent.parent.resolve()