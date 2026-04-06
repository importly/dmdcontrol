import time
from dlpc900_hid import DLPC900
from logger import setup_logger, logger

try:
    # We don't have args in wake_dp but let's just use INFO
    setup_logger(verbose=False)

    dlpc = DLPC900()
    logger.info("[+] Waking up DisplayPort receiver...")

    # IT6535 Power Mode (0x1A01): 2 = Power on DP Receiver
    dlpc.send_packet(0x1A01, bytes([2]))
    time.sleep(1)

    # DLPU018J Table 2-46: 0 = Parallel (DisplayPort receiver is routed to Parallel interface)
    dlpc.set_input_source(0, 1)
    dlpc.set_display_mode(0)
    dlpc.apply_block_lock_workaround()
    logger.info("[+] Done.")
except Exception as e:
    logger.exception(f"[ERROR] {e}")
