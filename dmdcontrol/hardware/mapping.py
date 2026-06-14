"""DMD mapping config for explicit USB/DisplayPort selection."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "dmd_devices.json"


@dataclass(frozen=True)
class DmdMapping:
    name: str
    usb_id_path: str
    usb_devpath_contains: str | None = None
    xrandr_output: str | None = None
    glfw_monitor_index: int | None = None
    target_hz: int | None = None


def _clean_optional_string(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def load_dmd_config(path=None):
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict) or not isinstance(config.get("dmds"), dict):
        raise ValueError(f"{config_path} must contain a top-level 'dmds' object")
    return config


def resolve_dmd_mapping(name, config_path=None):
    if not name:
        raise ValueError("DMD name is required")
    config = load_dmd_config(config_path)
    dmds = config["dmds"]
    if name not in dmds:
        known = ", ".join(sorted(dmds)) or "<none>"
        raise KeyError(f"DMD {name!r} is not configured. Known DMDs: {known}")
    raw = dmds[name]
    if not isinstance(raw, dict):
        raise ValueError(f"DMD {name!r} config must be an object")

    usb_id_path = _clean_optional_string(raw.get("usb_id_path"))
    if not usb_id_path:
        raise ValueError(f"DMD {name!r} config must define usb_id_path")

    monitor = raw.get("glfw_monitor_index")
    if monitor is not None:
        monitor = int(monitor)
        if monitor < 0:
            raise ValueError(f"DMD {name!r} glfw_monitor_index must be >= 0")

    target_hz = raw.get("target_hz")
    if target_hz is not None:
        target_hz = int(target_hz)
        if target_hz <= 0:
            raise ValueError(f"DMD {name!r} target_hz must be positive")

    return DmdMapping(
        name=name,
        usb_id_path=usb_id_path,
        usb_devpath_contains=_clean_optional_string(raw.get("usb_devpath_contains")),
        xrandr_output=_clean_optional_string(raw.get("xrandr_output")),
        glfw_monitor_index=monitor,
        target_hz=target_hz,
    )


def _build_parser():
    parser = argparse.ArgumentParser(description="Resolve configured DMD mapping values")
    parser.add_argument("--dmd", required=True, help="Configured DMD name, for example A or B")
    parser.add_argument("--config", default=None, help="Path to dmd_devices.json")
    parser.add_argument(
        "--field",
        choices=(
            "name",
            "usb_id_path",
            "usb_devpath_contains",
            "xrandr_output",
            "glfw_monitor_index",
            "target_hz",
        ),
        required=True,
        help="Field to print",
    )
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    mapping = resolve_dmd_mapping(args.dmd, args.config)
    value = getattr(mapping, args.field)
    print("" if value is None else str(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
