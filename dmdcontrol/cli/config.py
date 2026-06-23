from __future__ import annotations

import argparse
import json
from types import ModuleType

FIELDS = (
    "name",
    "usb_id_path",
    "usb_devpath_contains",
    "xrandr_output",
    "glfw_monitor_index",
)


def _mapping_module() -> ModuleType:
    from dmdcontrol.hardware import mapping

    return mapping


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Show resolved DMD mapping config")
    parser.add_argument("--dmd", required=True, help="Configured DMD name, for example A or B")
    parser.add_argument("--config", default=None, help="Path to dmd_devices.json")
    parser.add_argument("--field", choices=FIELDS, default=None, help="Print one resolved field")
    return parser


def show(argv: list[str]) -> int:
    args = _build_parser().parse_args(argv)
    mapping = _mapping_module().resolve_dmd_mapping(args.dmd, args.config)
    values = {field: getattr(mapping, field) for field in FIELDS}
    if args.field:
        value = values[args.field]
        print("" if value is None else value)
    else:
        print(json.dumps(values, sort_keys=True))
    return 0
