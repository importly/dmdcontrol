"""Camera integration helpers for DMD control."""

from .camera import (
    CameraProphsee,
    CameraProphesee,
    CameraDAVIS,
    BackgroundActivityNoiseFilter,
    EVENT_DTYPE,
)

# Default camera alias
Camera = CameraProphsee

__all__ = [
    "Camera",
    "CameraProphsee",
    "CameraProphesee",
    "CameraDAVIS",
    "BackgroundActivityNoiseFilter",
    "EVENT_DTYPE",
]
