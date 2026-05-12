"""
DMD warm-up script — replicates mentor's dmd_define() conditions.

Mentor's data_collection.py init called dmd_define() which:
  - Ran BOTH DMDs in mode 3 simultaneously
  - Used 1-second exposure per pattern (1e6 us)
  - Waited for two rounds of user input (1-3 min total)
The stable triggers that followed were a side effect of this long warmup.

This script replicates that: connects to ALL available DLPC900 devices,
loads mode 3 patterns on each, and runs for the given duration before
handing off to main.py (Video Pattern Mode).

After a power cycle use at least 60s. After a soft restart 30s usually works.

Usage:
    python test.py [duration_seconds]   # default: 60s
    ./run_dmd.sh --hz 60 ...            # run immediately after
"""

import sys
import time
import numpy as np
import usb.core
import pycrafter6500
from dmd_functions import dmd_pattern_load

VID = 0x0451
PID = 0xC900

WARMUP_DURATION_S = 60       # match original a305b90 working default; post-power-cycle needs ~60s
EXPOSURE_US       = 1_000_000  # 1 second per pattern — matches mentor's dmd_define() default
DARK_US           = 0
REPEAT            = 0        # infinite loop


def find_all_addresses():
    devices = usb.core.find(find_all=True)
    return [d.address for d in devices if d.idVendor == VID and d.idProduct == PID]


def main() -> None:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else WARMUP_DURATION_S

    addresses = find_all_addresses()
    if not addresses:
        print("[!] No DLPC900 devices found. Is the DMD connected?")
        sys.exit(1)

    print(f"[+] Found {len(addresses)} DLPC900 device(s) at addresses: {addresses}")

    # Solid white/black: ERLE compresses to near-zero size, uploads in ~1s each.
    # Pattern content doesn't affect DP clock stabilization — only duration matters.
    patterns = [
        np.full((1080, 1920), 255, dtype=np.uint8),  # all-white -> 1 after //129
        np.full((1080, 1920),   0, dtype=np.uint8),  # all-black -> 0 after //129
    ]

    dlps = []
    for addr in addresses:
        print(f"[+] Connecting to DLPC900 at address {addr}...")
        dlp = pycrafter6500.dmd(address_select=True, address=addr)
        print(f"    Loading mode 3 (Pattern On-The-Fly)...")
        print(f"    {len(patterns)} patterns  exposure={EXPOSURE_US}us  dark={DARK_US}us  repeat=infinite")
        dmd_pattern_load(
            dlp=dlp,
            pattern_file_list=patterns,
            exposure_val=EXPOSURE_US,
            dark_time_val=DARK_US,
            trigger_in_val=False,
            trigger_out_val=True,
            repeat=REPEAT,
            open_from_file=False,
        )
        dlp.startsequence()
        dlps.append(dlp)

    print(f"[+] All {len(dlps)} DMD(s) running mode 3. Warming up for {duration:.0f}s...")
    t0 = time.time()
    try:
        while True:
            elapsed = time.time() - t0
            if elapsed >= duration:
                break
            print(f"\r    {elapsed:5.1f}s / {duration:.0f}s", end="", flush=True)
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[!] Interrupted.")

    print(f"\n[+] Stopping and releasing USB ({len(dlps)} device(s))...")
    for dlp in dlps:
        dlp.stopsequence()
    for dlp in dlps:
        del dlp
    dlps.clear()
    time.sleep(0.5)

    print("[+] Warm-up done. Run:")
    print("    ./run_dmd.sh --hz 60 -v --seq-utilization 0.70 --test-snake --runtime-seconds 120")


if __name__ == "__main__":
    main()
