"""HTML assets for the local DMD preview server."""

from __future__ import annotations

from pathlib import Path

INDEX_HTML_PATH = Path(__file__).parent / "index.html"
INDEX_HTML = INDEX_HTML_PATH.read_text(encoding="utf-8")
