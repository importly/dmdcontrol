from __future__ import annotations

import argparse

from . import config, flood, pair, preview, single, usb


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

    flood_parser = subparsers.add_parser("flood")
    flood_actions = flood_parser.add_subparsers(dest="command", required=True)
    flood_actions.add_parser("run", add_help=False)

    config_parser = subparsers.add_parser("config")
    config_actions = config_parser.add_subparsers(dest="command", required=True)
    config_actions.add_parser("show", add_help=False)

    return parser


def main(argv: list[str] | None = None) -> int | None:
    args, passthrough = _build_parser().parse_known_args(argv)
    if args.area == "single" and args.command == "run":
        return single.run(passthrough)
    if args.area == "pair" and args.command == "run":
        return pair.run(passthrough)
    if args.area == "pair" and args.command == "calibrate":
        return pair.calibrate(passthrough)
    if args.area == "preview" and args.command == "serve":
        return preview.serve(passthrough)
    if args.area == "usb" and args.command == "discover":
        return usb.discover(passthrough)
    if args.area == "usb" and args.command == "wake":
        return usb.wake(passthrough)
    if args.area == "flood" and args.command == "run":
        return flood.run(passthrough)
    if args.area == "config" and args.command == "show":
        return config.show(passthrough)
    raise SystemExit(f"Unsupported command: {args.area} {args.command}")
