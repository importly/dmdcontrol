from __future__ import annotations

import argparse
import time
from types import ModuleType, SimpleNamespace


def _usb_module() -> ModuleType:
    from dmdcontrol.hardware import usb

    return usb


def _wake_dependencies() -> SimpleNamespace:
    from dmdcontrol.hardware.dlpc900 import DLPC900
    from dmdcontrol.hardware.mapping import resolve_dmd_mapping
    from dmdcontrol.support.logging import logger, setup_logger

    return SimpleNamespace(
        DLPC900=DLPC900,
        resolve_dmd_mapping=resolve_dmd_mapping,
        logger=logger,
        setup_logger=setup_logger,
    )


def _build_wake_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wake the DLPC900 DisplayPort receiver")
    parser.add_argument("--dmd", default=None, help="Configured DMD name from dmd_devices.json")
    parser.add_argument("--dmd-config", default=None, help="Path to DMD mapping config")
    return parser


def discover(argv: list[str]) -> int | None:
    return _usb_module().main(argv)


def wake(argv: list[str]) -> int | None:
    args, _unknown = _build_wake_parser().parse_known_args(argv)
    deps = _wake_dependencies()
    deps.setup_logger(verbose=False)

    mapping = deps.resolve_dmd_mapping(args.dmd, args.dmd_config) if args.dmd else None
    if mapping:
        deps.logger.info(
            f"[+] Waking DMD {mapping.name}: USB id_path={mapping.usb_id_path}, "
            f"expected devpath fragment={mapping.usb_devpath_contains or '<not required>'}")

    dlpc = deps.DLPC900(
        usb_id_path=mapping.usb_id_path if mapping else None,
        usb_devpath_contains=mapping.usb_devpath_contains if mapping else None,
    )
    deps.logger.info("[+] Waking up DisplayPort receiver...")

    dlpc.wake_displayport_receiver()
    time.sleep(1)

    dlpc.set_input_source(0, 1)
    dlpc.set_display_mode(0)
    dlpc.apply_block_lock_workaround()
    deps.logger.info("[+] Done.")
    return 0
