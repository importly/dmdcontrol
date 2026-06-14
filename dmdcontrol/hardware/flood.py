#!/usr/bin/env python3
"""
USB-only DLPC900 solid flood helper.

Purpose:
  Use ONE connected DLPC900 controller over USB to show a solid internal
  test-pattern field. No DisplayPort, no Xorg, no GLFW, no xinit.

Typical workflow:
  1. Plug in ONLY the DMD/controller you want to flood.
  2. Run: python -m dmdcontrol flood run --yes --white
  3. Disconnect that controller.
  4. Plug in the calibration DMD/controller and run run_calibr_square.sh.

Examples:
  python -m dmdcontrol flood run --yes
  python -m dmdcontrol flood run --yes --white
  python -m dmdcontrol flood run --yes --black
  python -m dmdcontrol flood run --yes --invert
  python -m dmdcontrol flood run --yes --black --invert
  python -m dmdcontrol flood run --yes --allow-multiple
"""

import argparse
import sys
import time

import usb.core

from dmdcontrol.hardware.dlpc900 import DLPC900

DLPC900_VID = 0x0451
DLPC900_PID = 0xC900

INTERNAL_PATTERN_WHITE_LEVEL = 0x03FF
INTERNAL_PATTERN_BLACK_LEVEL = 0x0000

DISPLAY_MODE_VIDEO = 0
INPUT_SOURCE_INTERNAL_TEST_PATTERN = 1
PARALLEL_BIT_DEPTH_24 = 1
PIXEL_FORMAT_RGB = 0
INTERNAL_TEST_PATTERN_SOLID_FIELD = 0


def _count_dlpc900_devices() -> int:
    devices = usb.core.find(
        find_all=True,
        idVendor=DLPC900_VID,
        idProduct=DLPC900_PID,
    )
    return sum(1 for _ in devices)


def configure_solid_flood(
    color: str,
    led_current: int,
    leave_leds_alone: bool,
) -> None:
    if color not in ("white", "black"):
        raise ValueError(f"Unsupported color: {color}")

    device_count = _count_dlpc900_devices()
    if device_count == 0:
        raise RuntimeError("No DLPC900 USB device found.")
    if device_count > 1:
        raise RuntimeError(
            f"Found {device_count} DLPC900 USB devices. "
            "Unplug the other controller or pass --allow-multiple if you accept "
            "that usb.core.find() will use the first matching device.")

    dlpc = DLPC900()

    # Make sure mirrors are not parked.
    try:
        dlpc.set_dmd_park(False)
        time.sleep(0.1)
    except Exception:
        pass

    if not leave_leds_alone:
        if not (0 <= led_current <= 255):
            raise ValueError(f"led_current must be in range 0..255, got {led_current}")
        dlpc.set_led_current(led_current, led_current, led_current)
        dlpc.set_led_enables(r=True, g=True, b=True, sequencer=True)
        time.sleep(0.1)

    # Video mode + internal test pattern generator.
    dlpc.set_display_mode(DISPLAY_MODE_VIDEO)
    time.sleep(0.1)

    dlpc.set_input_source(
        source=INPUT_SOURCE_INTERNAL_TEST_PATTERN,
        bit_depth_sel=PARALLEL_BIT_DEPTH_24,
    )
    time.sleep(0.1)

    dlpc.set_input_pixel_format(PIXEL_FORMAT_RGB)
    time.sleep(0.05)

    dlpc.set_internal_test_pattern_color(
        INTERNAL_PATTERN_WHITE_LEVEL if color == "white" else INTERNAL_PATTERN_BLACK_LEVEL)
    time.sleep(0.05)

    dlpc.set_internal_test_pattern(INTERNAL_TEST_PATTERN_SOLID_FIELD)
    time.sleep(0.2)

    try:
        display_mode = dlpc.get_display_mode()
        print(f"[status] display_mode={display_mode}")
    except Exception:
        pass

    try:
        main_status = dlpc.get_main_status()
        print(f"[status] main_status={main_status}")
    except Exception:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="USB-only DLPC900 solid white/black flood using internal test pattern mode.")

    color_group = parser.add_mutually_exclusive_group()
    color_group.add_argument(
        "--color",
        choices=("white",
                 "black"),
        default=None,
        help="Requested flood color. Default: white.",
    )
    color_group.add_argument(
        "--white",
        action="store_const",
        const="white",
        dest="color_flag",
        help="Requested flood color: white.",
    )
    color_group.add_argument(
        "--black",
        action="store_const",
        const="black",
        dest="color_flag",
        help="Requested flood color: black.",
    )

    parser.add_argument(
        "--invert",
        action="store_true",
        help="Invert requested color: white->black, black->white.",
    )
    parser.add_argument(
        "--allow-multiple",
        action="store_true",
        help="Allow running when multiple DLPC900 USB devices are connected.",
    )
    parser.add_argument(
        "--led-current",
        type=int,
        default=255,
        help="RGB LED current byte value, 0..255. Default: 255.",
    )
    parser.add_argument(
        "--leave-leds-alone",
        action="store_true",
        help="Do not change LED enable/current settings.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive safety confirmation.",
    )

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    requested = args.color_flag or args.color or "white"
    output = ("black" if requested == "white" else "white") if args.invert else requested

    if not args.yes:
        print("This will configure the connected DLPC900 over USB.")
        print("Plug in ONLY the controller you want to flood.")
        print(f"Requested color: {requested}")
        print(f"Invert: {args.invert}")
        print(f"Effective output: {output}")
        answer = input("Continue? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 2

    device_count = _count_dlpc900_devices()
    if device_count > 1 and not args.allow_multiple:
        print(
            f"ERROR: Found {device_count} DLPC900 USB devices.\n"
            "Unplug the other controller, then rerun.\n"
            "Override only if intentional: --allow-multiple",
            file=sys.stderr,
        )
        return 1

    print("=== DLPC900 USB Solid Flood ===")
    print(f"Requested color: {requested}")
    print(f"Invert: {args.invert}")
    print(f"Effective output: {output}")

    try:
        configure_solid_flood(
            color=output,
            led_current=args.led_current,
            leave_leds_alone=args.leave_leds_alone,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Done. DMD should now be solid {output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
