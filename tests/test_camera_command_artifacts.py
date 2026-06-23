import sys

from dmdcontrol.camera.command_artifacts import camera_command_argv, command_text


def test_camera_command_argv_wraps_explicit_cli_args():
    assert camera_command_argv("pair-capture", ["--dry-run-timing", "-v"]) == [
        "python",
        "-m",
        "dmdcontrol",
        "camera",
        "pair-capture",
        "--dry-run-timing",
        "-v",
    ]


def test_camera_command_argv_uses_current_process_when_args_are_implicit(monkeypatch):
    current_argv = [
        "python",
        "-m",
        "dmdcontrol",
        "camera",
        "sync-check",
        "--dry-run",
    ]
    monkeypatch.setattr(sys, "argv", current_argv)

    assert camera_command_argv("sync-check", None) == current_argv


def test_command_text_quotes_shell_sensitive_args():
    text = command_text([
        "python",
        "-m",
        "dmdcontrol",
        "camera",
        "sync-check",
        "--name-override",
        "run 1",
    ])

    assert text == "python -m dmdcontrol camera sync-check --name-override 'run 1'\n"
