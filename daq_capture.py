"""
Digilent Analog Discovery 2 - DLPC900 Trigger Diagnostic Tool

Samples BOTH:
  - Analog scope channels (1+, 2+)   -- in case the wire is on the scope input
  - Digital IO channels (DIO 0-3)     -- in case the wire is on a digital pin

This way we find the signal no matter where it's physically wired.
"""
import time
import sys
from ctypes import *

def load_dwf():
    if sys.platform.startswith("win"):
        paths = [
            "C:\\Program Files\\Digilent\\WaveForms3\\dwf.dll",
            "C:\\Program Files (x86)\\Digilent\\WaveFormsSDK\\dwf.dll",
        ]
        for p in paths:
            try:
                return cdll.LoadLibrary(p)
            except OSError:
                continue
        print("ERROR: dwf.dll not found. Install Digilent WaveForms.")
        sys.exit(1)
    else:
        return cdll.LoadLibrary("libdwf.so")

def main():
    print("=" * 60)
    print("  AD2 Trigger Diagnostic - Scanning ALL channels")
    print("=" * 60)
    print("Close the WaveForms GUI before running!\n")

    dwf = load_dwf()

    hdwf = c_int()
    dwf.FDwfDeviceOpen(c_int(-1), byref(hdwf))
    if hdwf.value == 0:
        print("ERROR: No device found.")
        sys.exit(1)
    print(f"Device opened (handle={hdwf.value})\n")

    # ---- 1. ANALOG SCOPE: Sample channels 1 and 2 ----
    print("--- Phase 1: Analog Scope Channels (1+, 2+) ---")
    sample_rate = 1_000_000  # 1 MHz
    duration = 0.1           # 100 ms
    n_samples = int(sample_rate * duration)

    # Configure scope
    dwf.FDwfAnalogInFrequencySet(hdwf, c_double(sample_rate))
    dwf.FDwfAnalogInBufferSizeSet(hdwf, c_int(min(n_samples, 8192)))
    # Channel 1
    dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(0), c_bool(True))
    dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(0), c_double(5.0))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf, c_int(0), c_double(0.0))
    # Channel 2
    dwf.FDwfAnalogInChannelEnableSet(hdwf, c_int(1), c_bool(True))
    dwf.FDwfAnalogInChannelRangeSet(hdwf, c_int(1), c_double(5.0))
    dwf.FDwfAnalogInChannelOffsetSet(hdwf, c_int(1), c_double(0.0))

    # No trigger, just capture
    dwf.FDwfAnalogInTriggerSourceSet(hdwf, c_int(0))  # trigsrcNone
    dwf.FDwfAnalogInConfigure(hdwf, c_int(0), c_int(1))

    buf_size = min(n_samples, 8192)
    status = c_byte()
    t0 = time.time()
    while True:
        dwf.FDwfAnalogInStatus(hdwf, c_int(1), byref(status))
        if status.value == 2:
            break
        if time.time() - t0 > 3.0:
            print("  Timeout on analog capture")
            break
        time.sleep(0.005)

    ch1_buf = (c_double * buf_size)()
    ch2_buf = (c_double * buf_size)()
    dwf.FDwfAnalogInStatusData(hdwf, c_int(0), byref(ch1_buf), c_int(buf_size))
    dwf.FDwfAnalogInStatusData(hdwf, c_int(1), byref(ch2_buf), c_int(buf_size))

    ch1_min = min(ch1_buf)
    ch1_max = max(ch1_buf)
    ch1_avg = sum(ch1_buf) / len(ch1_buf)
    ch2_min = min(ch2_buf)
    ch2_max = max(ch2_buf)
    ch2_avg = sum(ch2_buf) / len(ch2_buf)

    # Count edges on analog channels (threshold at 1.5V)
    threshold = 1.5
    ch1_edges = 0
    ch1_prev = ch1_buf[0] > threshold
    for v in ch1_buf:
        cur = v > threshold
        if cur and not ch1_prev:
            ch1_edges += 1
        ch1_prev = cur

    ch2_edges = 0
    ch2_prev = ch2_buf[0] > threshold
    for v in ch2_buf:
        cur = v > threshold
        if cur and not ch2_prev:
            ch2_edges += 1
        ch2_prev = cur

    print(f"  Scope Ch1 (1+): min={ch1_min:.3f}V  max={ch1_max:.3f}V  avg={ch1_avg:.3f}V  rising_edges={ch1_edges}")
    print(f"  Scope Ch2 (2+): min={ch2_min:.3f}V  max={ch2_max:.3f}V  avg={ch2_avg:.3f}V  rising_edges={ch2_edges}")

    if ch1_max - ch1_min > 0.5:
        print(f"  >>> SIGNAL DETECTED on Scope Ch1! Swing = {ch1_max - ch1_min:.2f}V")
    if ch2_max - ch2_min > 0.5:
        print(f"  >>> SIGNAL DETECTED on Scope Ch2! Swing = {ch2_max - ch2_min:.2f}V")

    # ---- 2. DIGITAL IO: Sample DIO 0-15 ----
    print("\n--- Phase 2: Digital IO Channels (DIO 0-15) ---")

    hzSys = c_double()
    dwf.FDwfDigitalInInternalClockInfo(hdwf, byref(hzSys))
    dig_rate = 1_000_000
    divider = int(hzSys.value / dig_rate)
    dwf.FDwfDigitalInDividerSet(hdwf, c_int(divider))
    dwf.FDwfDigitalInSampleFormatSet(hdwf, c_int(16))

    dig_samples = min(n_samples, 32768)
    dwf.FDwfDigitalInBufferSizeSet(hdwf, c_int(dig_samples))
    dwf.FDwfDigitalInTriggerSourceSet(hdwf, c_int(0))  # trigsrcNone
    dwf.FDwfDigitalInConfigure(hdwf, c_int(0), c_int(1))

    t0 = time.time()
    while True:
        dwf.FDwfDigitalInStatus(hdwf, c_int(1), byref(status))
        if status.value == 2:
            break
        if time.time() - t0 > 3.0:
            print("  Timeout on digital capture")
            break
        time.sleep(0.005)

    dig_buf = (c_uint16 * dig_samples)()
    dwf.FDwfDigitalInStatusData(hdwf, byref(dig_buf), c_int(dig_samples * 2))

    # Analyze each DIO channel
    for ch in range(16):
        mask = 1 << ch
        total_high = sum(1 for v in dig_buf if v & mask)
        pct = (total_high / dig_samples) * 100

        edges = 0
        prev = bool(dig_buf[0] & mask)
        for v in dig_buf:
            cur = bool(v & mask)
            if cur and not prev:
                edges += 1
            prev = cur

        if edges > 0 or pct > 1.0:
            print(f"  DIO-{ch:2d}: HIGH {pct:6.2f}% | Rising edges: {edges:5d}  <<< ACTIVITY")
        # Always print DIO 0-3 for visibility
        elif ch < 4:
            print(f"  DIO-{ch:2d}: HIGH {pct:6.2f}% | Rising edges: {edges:5d}")

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    found = False
    if ch1_edges > 2:
        print(f"  Scope Ch1 (1+): {ch1_edges} pulses detected - trigger signal is HERE")
        found = True
    if ch2_edges > 2:
        print(f"  Scope Ch2 (2+): {ch2_edges} pulses detected - trigger signal is HERE")
        found = True

    for ch in range(16):
        mask = 1 << ch
        edges = 0
        prev = bool(dig_buf[0] & mask)
        for v in dig_buf:
            cur = bool(v & mask)
            if cur and not prev:
                edges += 1
            prev = cur
        if edges > 2:
            print(f"  DIO-{ch}: {edges} pulses detected - trigger signal is HERE")
            found = True

    if not found:
        print("  NO SIGNAL found on any channel.")
        print("  Check: Is the DMD running? Is the wire connected?")

    dwf.FDwfDeviceCloseAll()
    print("\nDone.")

if __name__ == "__main__":
    main()
