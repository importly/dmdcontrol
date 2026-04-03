import argparse
import time

from dlpc900_hid import DLPC900


TARGET_HZ = 60
BITPLANES = 24


def print_board_snapshot(dlpc, tag):
    print("\n" + "=" * 66)
    print(f"  DLPC900 Status Snapshot: {tag}")
    print("=" * 66)

    hw = dlpc.get_hardware_status()
    if hw is not None:
        print(f"Hardware Status raw: 0x{hw:02X}")
        print(f"  Internal init successful: {bool(hw & 0x01)}")
        print(f"  DMD compatibility error: {bool(hw & 0x02)}")
        print(f"  DMD reset ctrl error:    {bool(hw & 0x04)}")
        print(f"  Forced swap error:       {bool(hw & 0x08)}")
        print(f"  Sequence abort flag:     {bool(hw & 0x40)}")
        print(f"  Sequence error flag:     {bool(hw & 0x80)}")

    ms = dlpc.get_main_status()
    if ms:
        print(f"Main Status raw:      {ms['raw']}")
        print(f"  DMD parked:         {ms['dmd_parked']}")
        print(f"  Sequencer running:  {ms['sequencer_running']}")
        print(f"  Video frozen:       {ms['video_frozen']}")
        print(f"  External src lock:  {ms['external_source_locked']}")
        print(f"  Port1 sync valid:   {ms['port1_syncs_valid']}")
        print(f"  Port2 sync valid:   {ms['port2_syncs_valid']}")

    pc = dlpc.get_port_config()
    if pc:
        print(f"Port Config raw:      {pc['raw']}")
        print(f"  Pixel mode:         {pc['pixel_mode']}")
        print(f"  Pixel clock:        {pc['pixel_clock']}")
        print(f"  Data enable:        {pc['data_enable']}")
        print(f"  Sync select:        {pc['sync_select']}")

    dd = dlpc.get_display_dimensions()
    if dd:
        print("Display Dimensions:")
        print(f"  Total:              {dd['total_pixels_per_line']} x {dd['total_lines_per_frame']}")
        print(f"  Active:             {dd['active_pixels_per_line']} x {dd['active_lines_per_frame']}")
        print(f"  First pixel:        ({dd['first_active_pixel']}, {dd['first_active_line']})")
        print(f"  Pixel clock:        {dd['pixel_clock_khz']} kHz")

    err = dlpc.get_last_error()
    if err is not None:
        print(f"Last Error:           {err}")

    mode, err_flag = dlpc.get_display_mode()
    if mode is not None:
        print(f"Display Mode:         {mode} (error flag: {err_flag})")

    print("=" * 66 + "\n")


def build_lut_entries(target_hz):
    exposure_us = int((1_000_000 / target_hz) / BITPLANES)
    entries = []
    for bit_pos in range(BITPLANES):
        entries.append((bit_pos, exposure_us, True, 1, 7, 0, bit_pos))
    return entries, exposure_us


def wait_for_external_lock(dlpc, timeout_s=4.0):
    start = time.time()
    while time.time() - start < timeout_s:
        ms = dlpc.get_main_status()
        if ms and ms.get("external_source_locked"):
            return True
        time.sleep(0.2)
    return False


def configure_dlpc900_for_video_pattern(dlpc):
    print("Configuring DLPC900 for 1920x1080 @ 60Hz Video Pattern Mode (24 bit-planes)...")
    print("Following TI documentation sequence (DLPU018J Section 5.1)...")

    # Step 1: Stop any existing pattern playback
    dlpc.start_pattern_display(0)
    time.sleep(0.2)

    # Step 2: Configure LEDs
    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    # Step 3: Enter Video Mode (0) FIRST with DisplayPort source
    # Per DLPU018J p.56: "Must first change to Video Mode (0) with desired source enabled"
    print("  - Entering Video Mode (0) with DisplayPort source...")
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)  # DisplayPort
    dlpc.toggle_dual_pixel_mode(True)
    dlpc.apply_block_lock_workaround()

    # Step 4: Wait for sync lock (REQUIRED before mode 2 transition)
    print("  - Waiting for external source sync lock...")
    if wait_for_external_lock(dlpc, timeout_s=4.0):
        print("  - External source lock acquired. Ready for Video Pattern Mode.")
    else:
        print("  - [WARNING] External source lock not reported!")
        print("  - [WARNING] Video Pattern Mode transition may fail without sync lock.")

    # Step 5: Set display mode to Video Pattern Mode (0x02)
    # Per DLPU018J p.56: "Takes approximately 300ms to complete the transition"
    print("  - Switching to Video Pattern Mode (0x02)...")
    dlpc.set_display_mode(0x02)
    
    # CRITICAL: Wait 300ms for mode transition as per documentation
    print("  - Waiting 300ms for mode transition (per TI spec)...")
    time.sleep(0.3)
    
    dlpc.apply_block_lock_workaround()
    
    # Additional settling time
    time.sleep(0.1)

    # Step 6: Verify we're actually in mode 2
    mode, _ = dlpc.get_display_mode()
    print(f"  - Display mode readback: {mode} (expected: 2)")

    # Step 7: Define pattern LUT (bit-plane extraction)
    entries, exposure_us = build_lut_entries(TARGET_HZ)
    print(f"  - LUT: {BITPLANES} entries, exposure={exposure_us}us, binary rate={BITPLANES * TARGET_HZ} Hz")
    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(BITPLANES, repeat=True)
    
    # Step 8: Start pattern sequencer
    print("  - Starting pattern sequencer...")
    dlpc.start_pattern_display(2)
    time.sleep(0.2)

    # Verify mode stuck
    mode, _ = dlpc.get_display_mode()
    if mode != 2:
        print(f"  - [WARNING] Mode readback shows {mode}, not 2! Retrying...")
        dlpc.set_display_mode(0x02)
        time.sleep(0.3)
        dlpc.apply_block_lock_workaround()
        dlpc.start_pattern_display(2)
        time.sleep(0.2)
        mode, _ = dlpc.get_display_mode()
        print(f"  - After retry, mode readback: {mode}")


def verify_runtime_state(dlpc):
    ms = dlpc.get_main_status() or {}
    dd = dlpc.get_display_dimensions() or {}
    mode, _ = dlpc.get_display_mode()

    checks = {
        "display_mode_is_video_pattern": mode == 2,
        "sequencer_running": bool(ms.get("sequencer_running", False)),
        # Note: external_source_locked reports False even in working configurations
        # Note: display dimensions readback shows garbage during config, not reliable for verification
        # Note: No longer using hardware crop (512x512) - testing full 1920x1080 input
    }

    print("Verification:")
    for name, ok in checks.items():
        print(f"  {name:30} {'PASS' if ok else 'FAIL'}")

    all_ok = all(checks.values())
    if not all_ok:
        print("[WARNING] Runtime verification checks failed!")
        print("           Video Pattern Mode (2) not active or sequencer not running.")
        print("           Check DisplayPort sync lock and mode transition timing.")
    else:
        print("[OK] Runtime verification passed (mode=VideoPattern, sequencer running).")
    return all_ok


def run():
    parser = argparse.ArgumentParser(description="DLPC900 1080p60 Video Pattern Runtime")
    parser.add_argument("--hz", type=int, default=60, help="Only 60Hz is supported")
    parser.add_argument("--monitor", type=int, default=0, help="GLFW monitor index")
    parser.add_argument("--test-checkerboard", action="store_true", help="Display static checkerboard for runtime")
    parser.add_argument("--test-ordering", action="store_true", help="Display bit-ordering diagnostic for 60s")
    parser.add_argument("--test-numbered", action="store_true", help="Display numbered region diagnostic")
    parser.add_argument("--runtime-seconds", type=int, default=60, help="Runtime for diagnostic patterns")
    parser.add_argument("--wake-dp", action="store_true", help="Wake DP receiver in main.py (normally done by run_dmd.sh)")
    args = parser.parse_args()

    if args.hz != TARGET_HZ:
        raise SystemExit("Only 60Hz mode is supported in this setup. Use --hz 60.")

    dlpc = None
    engine = None
    try:
        print("Initializing DLPC900...")
        dlpc = DLPC900()

        if args.wake_dp:
            print("Waking up DisplayPort receiver...")
            dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        configure_dlpc900_for_video_pattern(dlpc)

        print_board_snapshot(dlpc, "POST-CONFIG (before GL stream)")

        from pattern_engine import PatternEngine
        engine = PatternEngine(monitor_index=args.monitor, fps=TARGET_HZ)

        # Generate initial frame based on test mode
        if args.test_ordering:
            print("Starting Diagnostic Mode: Bit Ordering Sweep...")
            patterns = engine.generate_ordering_diagnostic_patterns(1920, 1080)
        elif args.test_numbered:
            print("Starting Diagnostic Mode: Numbered Regions (6x4 grid)...")
            from debug_numbered_regions import generate_numbered_regions
            numbered_rgb = generate_numbered_regions(1920, 1080, grid_cols=6, grid_rows=4)
            # Convert RGB to 24 binary patterns
            patterns = engine.rgb_to_binary_patterns(numbered_rgb)
        else:
            print("Starting Diagnostic Mode: Static Checkerboard...")
            patterns = engine.generate_checkerboard()
        
        frame = engine.pack_patterns(patterns)
        engine.display_frame(frame)

        time.sleep(1.0)
        print_board_snapshot(dlpc, "POST-FIRST-FRAME (after GL stream)")
        verify_runtime_state(dlpc)

        hold_s = args.runtime_seconds if (args.test_checkerboard or args.test_ordering or args.test_numbered) else 15
        print(f"Holding output for {hold_s} seconds...")
        if args.test_checkerboard or args.test_numbered:
            # Static pattern - just hold
            time.sleep(hold_s)
        else:
            # Dynamic pattern - update each frame
            end_t = time.time() + hold_s
            while time.time() < end_t and not engine.should_close():
                if args.test_ordering:
                    patterns = engine.generate_ordering_diagnostic_patterns(1920, 1080)
                else:
                    patterns = engine.generate_checkerboard()
                frame = engine.pack_patterns(patterns)
                engine.display_frame(frame)

    except Exception as exc:
        print(f"[ERROR] Runtime failed: {exc}")
        if dlpc is not None:
            print("Keeping DLPC900 configured for 10 seconds for observation...")
            time.sleep(10)
    finally:
        print("Cleaning up...")
        if dlpc is not None:
            dlpc.start_pattern_display(0)
            dlpc.set_display_mode(0x00)
            dlpc.apply_block_lock_workaround()
        if engine is not None:
            engine.cleanup()


if __name__ == "__main__":
    run()
