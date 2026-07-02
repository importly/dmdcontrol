from unittest import mock

from dmdcontrol.runtime import single as main


def test_main_accepts_argv_and_returns_zero_for_dry_run_timing():
    with mock.patch.object(main, "_dry_run_timing") as dry_run_timing:
        result = main.main(["--dry-run-timing", "--test", "checkerboard"])

    assert result == 0
    dry_run_timing.assert_called_once()
