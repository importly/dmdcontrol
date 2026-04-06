#!/usr/bin/env python3
import time
from dlpc900_hid import DLPC900


def main():
    dlpc = DLPC900()

    print("Writing: display mode 0 (video)...")
    dlpc.set_display_mode(0)
    time.sleep(0.1)

    mode, err = dlpc.get_display_mode()
    print(f"Readback display mode: mode={mode}, err={err}")

    print("Writing: port config dual-pixel...")
    dlpc.toggle_dual_pixel_mode(True)
    time.sleep(0.1)

    pc = dlpc.get_port_config()
    print(f"Readback port config: {pc}")

    print("Reading main status...")
    ms = dlpc.get_main_status()
    print(f"Main status: {ms}")

    print("Reading hardware status...")
    hw = dlpc.get_hardware_status()
    print(f"Hardware status raw: {hw}")


if __name__ == "__main__":
    main()
