from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable

CALIBRATION_TEST = "a-calibr-square-b-dot"
CONFIG_FIELDS = (
    "name",
    "usb_id_path",
    "usb_devpath_contains",
    "xrandr_output",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m dmdcontrol")
    subparsers = parser.add_subparsers(dest="area", required=True)

    pair_parser = subparsers.add_parser("pair")
    pair_actions = pair_parser.add_subparsers(dest="command", required=True)
    pair_actions.add_parser("run", add_help=False)
    pair_actions.add_parser("calibrate", add_help=False)

    preview_parser = subparsers.add_parser("preview")
    preview_actions = preview_parser.add_subparsers(dest="command", required=True)
    preview_actions.add_parser("serve", add_help=False)

    usb_parser = subparsers.add_parser("usb")
    usb_actions = usb_parser.add_subparsers(dest="command", required=True)
    usb_actions.add_parser("discover", add_help=False)
    usb_actions.add_parser("wake", add_help=False)

    config_parser = subparsers.add_parser("config")
    config_actions = config_parser.add_subparsers(dest="command", required=True)
    config_actions.add_parser("show", add_help=False)

    camera_parser = subparsers.add_parser("camera")
    camera_actions = camera_parser.add_subparsers(dest="command", required=True)
    camera_actions.add_parser("discover", add_help=False)
    camera_actions.add_parser("status", add_help=False)
    camera_actions.add_parser("sync-check", add_help=False)
    camera_actions.add_parser("pair-capture", add_help=False)
    camera_actions.add_parser("reprocess-aedat4", add_help=False)

    return parser


def _translate_pair_run_args(argv: list[str]) -> list[str]:
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


def _pair_run(argv: list[str]) -> int | None:
    from dmdcontrol.runtime.pair import main as runtime_main

    return runtime_main(_translate_pair_run_args(argv))


def _pair_calibrate(argv: list[str]) -> int | None:
    from dmdcontrol.runtime.pair import main as runtime_main

    translated = ["--test", CALIBRATION_TEST]
    if not any(
        arg == "--runtime-seconds" or arg.startswith("--runtime-seconds=")
        for arg in argv
    ):
        translated.extend(["--runtime-seconds", "0"])
    translated.extend(argv)
    return runtime_main(translated)


def _preview_serve(argv: list[str]) -> int | None:
    from dmdcontrol.preview.server import main as server_main

    return server_main(argv)


def _usb_discover(argv: list[str]) -> int | None:
    from dmdcontrol.hardware.usb import main as usb_main

    return usb_main(argv)


def _usb_wake(argv: list[str]) -> int | None:
    from dmdcontrol.hardware.dlpc900 import DLPC900
    from dmdcontrol.hardware.mapping import resolve_dmd_mapping
    from dmdcontrol.support.logging import logger, setup_logger

    parser = argparse.ArgumentParser(
        description="Wake the DLPC900 DisplayPort receiver"
    )
    parser.add_argument(
        "--dmd", default=None, help="Configured DMD name from dmd_devices.json"
    )
    parser.add_argument("--dmd-config", default=None, help="Path to DMD mapping config")
    args, _unknown = parser.parse_known_args(argv)
    setup_logger(verbose=False)

    mapping = resolve_dmd_mapping(args.dmd, args.dmd_config) if args.dmd else None
    if mapping:
        logger.info(
            f"[+] Waking DMD {mapping.name}: USB id_path={mapping.usb_id_path}, "
            f"expected devpath fragment={mapping.usb_devpath_contains or '<not required>'}"
        )

    dlpc = DLPC900(
        usb_id_path=mapping.usb_id_path if mapping else None,
        usb_devpath_contains=mapping.usb_devpath_contains if mapping else None,
    )
    logger.info("[+] Waking up DisplayPort receiver...")
    dlpc.wake_displayport_receiver()
    time.sleep(1)
    dlpc.set_input_source(0, 1)
    dlpc.set_display_mode(0)
    dlpc.apply_block_lock_workaround()
    logger.info("[+] Done.")
    return 0


def _config_show(argv: list[str]) -> int:
    from dmdcontrol.hardware.mapping import resolve_dmd_mapping

    parser = argparse.ArgumentParser(description="Show resolved DMD mapping config")
    parser.add_argument(
        "--dmd", required=True, help="Configured DMD name, for example A or B"
    )
    parser.add_argument("--config", default=None, help="Path to dmd_devices.json")
    parser.add_argument(
        "--field",
        choices=CONFIG_FIELDS,
        default=None,
        help="Print one resolved field",
    )
    args = parser.parse_args(argv)
    mapping = resolve_dmd_mapping(args.dmd, args.config)
    values = {field: getattr(mapping, field) for field in CONFIG_FIELDS}
    if args.field:
        value = values[args.field]
        print("" if value is None else value)
    else:
        print(json.dumps(values, sort_keys=True))
    return 0


def _camera_discover(_argv: list[str]) -> int:
    from dmdcontrol.camera.discovery import discover_cameras

    print(json.dumps(discover_cameras(), indent=2, sort_keys=True))
    return 0


def _camera_status(_argv: list[str]) -> int:
    from dmdcontrol.camera.discovery import camera_status

    print(json.dumps(camera_status(), indent=2, sort_keys=True))
    return 0


def _camera_sync_check(argv: list[str]) -> int | None:
    from dmdcontrol.camera import sync_check

    return sync_check.main(argv)


def _camera_pair_capture(argv: list[str]) -> int | None:
    from dmdcontrol.camera import pair_capture

    return pair_capture.main(argv)


def _camera_reprocess_aedat4(argv: list[str]) -> int | None:
    from dmdcontrol.camera import reprocess_aedat4

    return reprocess_aedat4.main(argv)


_COMMAND_HANDLERS: dict[tuple[str, str], Callable[[list[str]], int | None]] = {
    ("pair", "run"): _pair_run,
    ("pair", "calibrate"): _pair_calibrate,
    ("preview", "serve"): _preview_serve,
    ("usb", "discover"): _usb_discover,
    ("usb", "wake"): _usb_wake,
    ("config", "show"): _config_show,
    ("camera", "discover"): _camera_discover,
    ("camera", "status"): _camera_status,
    ("camera", "sync-check"): _camera_sync_check,
    ("camera", "pair-capture"): _camera_pair_capture,
    ("camera", "reprocess-aedat4"): _camera_reprocess_aedat4,
}


def main(argv: list[str] | None = None) -> int | None:
    args, passthrough = _build_parser().parse_known_args(argv)
    command = (args.area, args.command)
    handler = _COMMAND_HANDLERS.get(command)
    if handler is None:
        raise SystemExit(f"Unsupported command: {args.area} {args.command}")
    return handler(passthrough)
