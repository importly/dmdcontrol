from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class _SupportsInt(Protocol):

    def __int__(self) -> int: ...


def as_int(value: object, *, name: str = "value") -> int:
    """Convert a validated dynamic record value to an integer."""
    if isinstance(value, (str, bytes, bytearray, _SupportsInt)):
        return int(value)
    raise TypeError(f"{name} must be integer-convertible, got {type(value).__name__}")
