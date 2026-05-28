from __future__ import annotations

from types import ModuleType

CALIBRATION_TEST = "a-calibr-square-b-dot"


def _pair_runtime() -> ModuleType:
    from dmdcontrol.runtime import pair

    return pair


def _translate_run_args(argv: list[str]) -> list[str]:
    translated = []
    for arg in argv:
        if arg == "--mode":
            translated.append("--test")
        elif arg.startswith("--mode="):
            translated.append("--test=" + arg.split("=", 1)[1])
        elif arg == "--b-test":
            translated.append("--test-b")
        elif arg.startswith("--b-test="):
            translated.append("--test-b=" + arg.split("=", 1)[1])
        else:
            translated.append(arg)
    return translated


def _has_runtime_seconds(argv: list[str]) -> bool:
    return any(arg == "--runtime-seconds" or arg.startswith("--runtime-seconds=") for arg in argv)


def run(argv: list[str]) -> int | None:
    return _pair_runtime().main(_translate_run_args(argv))


def calibrate(argv: list[str]) -> int | None:
    translated = ["--test", CALIBRATION_TEST]
    if not _has_runtime_seconds(argv):
        translated.extend(["--runtime-seconds", "0"])
    translated.extend(argv)
    return _pair_runtime().main(translated)
