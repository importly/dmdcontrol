from unittest import mock

from dmdcontrol.hardware import flood as flood_white_usb
from dmdcontrol.runtime import single as main


def test_main_accepts_argv_and_returns_zero_for_dry_run_timing():
    with mock.patch.object(main, "_dry_run_timing") as dry_run_timing:
        result = main.main(["--dry-run-timing", "--test", "checkerboard"])

    assert result == 0
    dry_run_timing.assert_called_once()


def test_flood_white_usb_accepts_argv_and_returns_two_when_cancelled():
    with mock.patch("builtins.input", return_value="n"):
        result = flood_white_usb.main(["--color", "white"])

    assert result == 2
