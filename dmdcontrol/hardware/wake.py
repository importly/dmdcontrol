import argparse
import time

from dmdcontrol.hardware.mapping import resolve_dmd_mapping
from dmdcontrol.hardware.dlpc900 import DLPC900
from dmdcontrol.support.logging import logger, setup_logger


def _build_parser():
    parser = argparse.ArgumentParser(description="Wake the DLPC900 DisplayPort receiver")
    parser.add_argument("--dmd", default=None, help="Configured DMD name from dmd_devices.json")
    parser.add_argument("--dmd-config", default=None, help="Path to DMD mapping config")
    return parser


def main(argv=None):
    args, _ = _build_parser().parse_known_args(argv)
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

    # IT6535 Power Mode (0x1A01): 2 = Power on DP Receiver
    dlpc.send_packet(0x1A01, bytes([2]))
    time.sleep(1)

    # DLPU018J Table 2-46: 0 = Parallel (DisplayPort receiver is routed to Parallel interface)
    dlpc.set_input_source(0, 1)
    dlpc.set_display_mode(0)
    dlpc.apply_block_lock_workaround()
    logger.info("[+] Done.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        logger.exception(f"[ERROR] {e}")
        raise SystemExit(1)
