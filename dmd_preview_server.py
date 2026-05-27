"""Compatibility shim for the DMD preview server."""

from __future__ import annotations

from dmdcontrol.preview.server import (
    BITPLANE_LABELS,
    DmdPreviewHandler,
    DmdPreviewServer,
    INDEX_HTML,
    LiveFrameStore,
    PAIR_TESTS,
    PATTERN_NAMES,
    STATIC_PAIR_TESTS,
    create_server,
    main,
    render_png_bytes,
    render_preview_png,
    render_view_image,
)

__all__ = [
    "BITPLANE_LABELS",
    "DmdPreviewHandler",
    "DmdPreviewServer",
    "INDEX_HTML",
    "LiveFrameStore",
    "PAIR_TESTS",
    "PATTERN_NAMES",
    "STATIC_PAIR_TESTS",
    "create_server",
    "main",
    "render_png_bytes",
    "render_preview_png",
    "render_view_image",
]


if __name__ == "__main__":
    raise SystemExit(main())
