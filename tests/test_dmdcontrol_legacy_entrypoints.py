from dmdcontrol.runtime import single as main


def test_main_parser_accepts_argv_for_live_runtime_options():
    args = main._build_parser().parse_args(["--test", "checkerboard", "--runtime-seconds", "1"])

    assert args.test == "checkerboard"
    assert args.runtime_seconds == 1