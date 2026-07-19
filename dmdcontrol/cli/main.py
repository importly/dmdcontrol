from __future__ import annotations

import argparse


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m dmdcontrol")
    subparsers = parser.add_subparsers(dest="area", required=True)

    single_parser = subparsers.add_parser("single")
    single_actions = single_parser.add_subparsers(dest="command", required=True)
    single_actions.add_parser("run", add_help=False)

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


def main(argv: list[str] | None = None) -> int | None:
    args, passthrough = _build_parser().parse_known_args(argv)
    if args.area == "single" and args.command == "run":
        from dmdcontrol.cli import single

        return single.run(passthrough)
    if args.area == "pair" and args.command == "run":
        from dmdcontrol.cli import pair

        return pair.run(passthrough)
    if args.area == "pair" and args.command == "calibrate":
        from dmdcontrol.cli import pair

        return pair.calibrate(passthrough)
    if args.area == "preview" and args.command == "serve":
        from dmdcontrol.cli import preview

        return preview.serve(passthrough)
    if args.area == "usb" and args.command == "discover":
        from dmdcontrol.cli import usb_discover

        return usb_discover.discover(passthrough)
    if args.area == "usb" and args.command == "wake":
        from dmdcontrol.cli import usb

        return usb.wake(passthrough)
    if args.area == "config" and args.command == "show":
        from dmdcontrol.cli import config

        return config.show(passthrough)
    if args.area == "camera" and args.command in {"discover", "status"}:
        from dmdcontrol.cli import camera

        return {"discover": camera.discover, "status": camera.status}[args.command](passthrough)
    if args.area == "camera" and args.command == "sync-check":
        from dmdcontrol.camera import sync_check

        return sync_check.main(passthrough)
    if args.area == "camera" and args.command == "pair-capture":
        from dmdcontrol.camera import pair_capture

        return pair_capture.main(passthrough)
    if args.area == "camera" and args.command == "reprocess-aedat4":
        from dmdcontrol.camera import reprocess_aedat4

        return reprocess_aedat4.main(passthrough)
    raise SystemExit(f"Unsupported command: {args.area} {args.command}")
