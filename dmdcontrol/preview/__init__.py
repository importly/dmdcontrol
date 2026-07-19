"""Preview server package for DMD control tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dmdcontrol.preview.server import (
        DmdPreviewHandler,
        DmdPreviewServer,
        create_server,
        main,
    )

__all__ = [
    "DmdPreviewHandler",
    "DmdPreviewServer",
    "create_server",
    "main",
]


def __getattr__(name):
    if name in __all__:
        from dmdcontrol.preview import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
