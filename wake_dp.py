import time
from dlpc900_hid import DLPC900

try:
    dlpc = DLPC900()
    print('Waking up DisplayPort receiver...')
    # IT6535 Power Mode: 2 = DisplayPort
    dlpc.send_packet(0x1A01, bytes([2]))
    time.sleep(1)
    
    # Also set input source to parallel (0) and 24-bit (1)
    dlpc.set_input_source(0, 1)
    # Set to Video Mode
    dlpc.set_display_mode(0)
    dlpc.apply_block_lock_workaround()
    print('Done.')
except Exception as e:
    print(f'Error: {e}')
