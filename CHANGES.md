# Video Pattern Mode Configuration Fix

## Problem Identified

The DLPC900 was not properly entering Video Pattern Mode (mode 2), causing:
- Display Mode readback showing 0 (Video Mode) instead of 2 (Video Pattern Mode)
- Sequencer not running
- Severe geometry distortion (stretched rectangles instead of squares)

## Root Cause

The configuration sequence was **not following TI documentation** (DLPU018J Section 5.1):

### What the code was doing WRONG:
1. Enter Video Mode (0) ✓
2. Wait for sync lock ✓
3. Switch to Video Pattern Mode (2) ✓
4. **Apply 512x512 hardware crop AFTER mode switch** ❌
5. Define patterns
6. Start sequencer

### What TI documentation requires:
1. Enter Video Mode (0) with desired source enabled
2. **Wait for sync lock** (CRITICAL)
3. Switch to Video Pattern Mode (2)
4. **Wait 300ms for mode transition to complete** (CRITICAL)
5. Define patterns
6. Set pattern count
7. Start sequencer

## Changes Made

### 1. Removed Hardware Crop
- **Removed:** `dlpc.set_input_display_resolution(704, 284, 512, 512)` call
- **Reason:** Not required for Video Pattern Mode, may interfere with mode transition
- **Effect:** System will now use full 1920x1080 input (no cropping or scaling)

### 2. Fixed Mode Transition Timing
- **Added:** Explicit 300ms wait after `set_display_mode(0x02)` per TI spec
- **Added:** Better diagnostic messages during transition
- **Added:** Mode verification after transition with retry logic

### 3. Improved Diagnostic Output
- Created `debug_numbered_regions.py` to generate numbered region patterns
- Better visualization of geometry distortion (if any remains)

## Files Modified

- `main.py` - Fixed `configure_dlpc900_for_video_pattern()` function
- `main.py` - Updated `verify_runtime_state()` function

## Files Created

- `debug_numbered_regions.py` - Diagnostic pattern generator
- `CHANGES.md` - This document

## Expected Behavior After Fix

### If successful:
1. Display Mode readback will show **2** (Video Pattern Mode)
2. Sequencer will report **running**
3. Checkerboard pattern will display with **correct square geometry** (no stretching)
4. Full 1920x1080 input will be used (24 bit-planes at 60Hz = 1440 binary patterns/sec)

### If still failing:
1. Check DisplayPort sync lock status in diagnostics
2. Verify X11 is sending 1920x1080@60Hz to DP-2
3. Check for timing-related issues in DLPC900 firmware

## Test Plan

### Step 1: Deploy to remote system
```bash
./sync_dmd.ps1
```

### Step 2: Run on remote system
```bash
ssh main@REMOTE_HOST
cd ~/dmd_project
./run_dmd.sh
```

### Step 3: Check diagnostic output
Look for:
- "External source lock acquired" message
- "Display mode readback: 2" (not 0)
- "Verification: display_mode_is_video_pattern PASS"
- "Verification: sequencer_running PASS"

### Step 4: Visual inspection
Observe physical DMD output:
- Should see checkerboard pattern
- Squares should be geometrically correct (not stretched)
- Pattern should cover full DMD area

### Step 5: Generate numbered diagnostics (if geometry still wrong)
```bash
# On local machine
python debug_numbered_regions.py

# Deploy and test
./sync_dmd.ps1
ssh main@REMOTE_HOST "cd ~/dmd_project && ./run_dmd.sh"
```

## References

- **DLPU018J** Section 2.4.1 (Display Mode Selection) - Page 56
- **DLPU018J** Section 5.1 (Video Pattern Mode Example) - Page 84
- **DLPT028** (Errata) - Block Lock Workaround

## Next Steps

1. Test with current changes (no crop, proper timing)
2. If mode 2 latches but geometry still wrong, investigate DisplayPort input format
3. If mode 2 still doesn't latch, add verbose USB HID traffic logging
4. Consider testing with different video timings (reduced blanking, etc.)
