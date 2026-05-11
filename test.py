"""
DMD warm-up script.

Replicates the conditions of the one confirmed-working run: mentor's pycrafter6500
code ran mode 3 (Pattern On-The-Fly) with real patterns for an extended period before
Video Pattern Mode was initialized — stable DP pixel clock, USB HID exercised.

Usage:
    python test.py [duration_seconds]   # default: 60s
    ./run_dmd.sh --hz 60 ...            # run main.py immediately after
"""

import sys
import time
import numpy as np
import pycrafter6500
from dmd_functions import dmd_pattern_load


WARMUP_DURATION_S = 60
NUM_PATTERNS      = 24       # fills one ERLE block exactly
EXPOSURE_US       = 5000     # 5ms — matches mentor's 200Hz data collection cadence
DARK_US           = 0
REPEAT            = 0        # infinite loop


def main() -> None:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else WARMUP_DURATION_S

    print("[+] Connecting to DLPC900 via USB...")
    dlp = pycrafter6500.dmd()

    print(f"[+] Generating {NUM_PATTERNS} random 1920x1080 binary patterns...")
    rng = np.random.default_rng(seed=0xDEAD)
    # Values 0 or 255 — dmd_pattern_load does //129 internally → 0 or 1
    patterns = [rng.integers(0, 2, (1080, 1920), dtype=np.uint8) * 255
                for _ in range(NUM_PATTERNS)]

    print(f"[+] Loading into mode 3 (Pattern On-The-Fly) via dmd_pattern_load...")
    print(f"    exposure={EXPOSURE_US}us  dark={DARK_US}us  repeat=infinite")
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

    print(f"[+] Mode 3 running. Warming up for {duration:.0f}s...")
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

    print(f"\n[+] Stopping and releasing USB...")
    dlp.stopsequence()
    del dlp
    time.sleep(0.5)

    print("[+] Warm-up done. Run:")
    print("    ./run_dmd.sh --hz 60 -v --seq-utilization 0.70 --test-snake --runtime-seconds 120")


if __name__ == "__main__":
    main()
