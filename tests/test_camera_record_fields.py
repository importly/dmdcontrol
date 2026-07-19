import numpy as np
import pytest

from dmdcontrol.camera.record_fields import as_int


class _IntegerLike:

    def __int__(self) -> int:
        return 17


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (12, 12),
        ("13", 13),
        (np.int64(14), 14),
        (_IntegerLike(), 17),
    ],
)
def test_as_int_accepts_supported_dynamic_values(value, expected):
    assert as_int(value, name="timestamp") == expected


def test_as_int_rejects_nonconvertible_dynamic_values():
    with pytest.raises(TypeError, match="timestamp must be integer-convertible"):
        as_int(object(), name="timestamp")
