import time
from dlpc900_hid import DLPC900

try:
    dlpc = DLPC900()
    print("Waking up DisplayPort receiver...")

    # IT6535 Power Mode (0x1A01): 2 = Power on DP Receiver
    dlpc.send_packet(0x1A01, bytes([2]))
    time.sleep(1)

    # CRITICAL FIX: set_input_source(source, bit_depth)
    # DLPU018J Table 2-46: 0 = Parallel, 1 = Internal Pattern, 2 = Flash, 3 = FPD-link, 4 = DisplayPort
    # Wait, the documentation says DisplayPort is often source=1 on DLP6500 EVM. Let's check Table 2-46 again.
    # Actually, main.py uses set_input_source(0, 1) in one place but configure_dlpc900_for_video_pattern uses set_input_source(0, 1)
    # Wait, let's look at DLPU018J Section 2.3.1.1 (0x1A00)
    # 0 = Parallel interface
    # 1 = Internal test pattern
    # 2 = Flash
    # 3 = FPD-link
    # We want DisplayPort! On the DLPC900 EVM, the DisplayPort receiver (IT6535) outputs to the Parallel interface of the DLPC900.
    # Therefore, source = 0 (Parallel) is correct for the DLPC900.
    # However, maybe we should also set port config?

    dlpc.set_input_source(0, 1)
    dlpc.set_display_mode(0)
    dlpc.apply_block_lock_workaround()
    print("Done.")
except Exception as e:
    print(f"Error: {e}")
