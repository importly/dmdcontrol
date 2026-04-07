import argparse
import time

try:
    import cv2
except ImportError:
    cv2 = None

from dlpc900_hid import DLPC900
from logger import setup_logger, logger


def generate_solid_color(color_idx, width=1920, height=1080):
    import numpy as np

    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, color_idx] = 255
    return img


TARGET_HZ = 60
BITPLANES = 24


def log_board_snapshot(dlpc, tag):
    logger.debug("=" * 66)
    logger.debug(f"  DLPC900 Status Snapshot: {tag}")
    logger.debug("=" * 66)

    hw = dlpc.get_hardware_status()
    if hw is not None:
        logger.debug(f"Hardware Status raw: 0x{hw:02X}")
        logger.debug(f"  Internal init successful: {bool(hw & 0x01)}")
        logger.debug(f"  DMD compatibility error: {bool(hw & 0x02)}")
        logger.debug(f"  DMD reset ctrl error:    {bool(hw & 0x04)}")
        logger.debug(f"  Forced swap error:       {bool(hw & 0x08)}")
        logger.debug(f"  Sequence abort flag:     {bool(hw & 0x40)}")
        logger.debug(f"  Sequence error flag:     {bool(hw & 0x80)}")

    ms = dlpc.get_main_status()
    if ms:
        logger.debug(f"Main Status raw:      {ms['raw']}")
        logger.debug(f"  DMD parked:         {ms['dmd_parked']}")
        logger.debug(f"  Sequencer running:  {ms['sequencer_running']}")
        logger.debug(f"  Video frozen:       {ms['video_frozen']}")
        logger.debug(f"  External src lock:  {ms['external_source_locked']}")
        logger.debug(f"  Port1 sync valid:   {ms['port1_syncs_valid']}")
        logger.debug(f"  Port2 sync valid:   {ms['port2_syncs_valid']}")

    pc = dlpc.get_port_config()
    if pc:
        logger.debug(f"Port Config raw:      {pc['raw']}")
        logger.debug(f"  Pixel mode:         {pc['pixel_mode']}")
        logger.debug(f"  Pixel clock:        {pc['pixel_clock']}")
        logger.debug(f"  Data enable:        {pc['data_enable']}")
        logger.debug(f"  Sync select:        {pc['sync_select']}")

    dd = dlpc.get_display_dimensions()
    if dd:
        logger.debug("Display Dimensions:")
        logger.debug(
            f"  Total:              {dd['total_pixels_per_line']} x {dd['total_lines_per_frame']}"
        )
        logger.debug(
            f"  Active:             {dd['active_pixels_per_line']} x {dd['active_lines_per_frame']}"
        )
        logger.debug(
            f"  First pixel:        ({dd['first_active_pixel']}, {dd['first_active_line']})"
        )
        logger.debug(f"  Pixel clock:        {dd['pixel_clock_khz']} kHz")

    err = dlpc.get_last_error()
    if err is not None:
        logger.debug(f"Last Error:           {err}")

    mode, err_flag = dlpc.get_display_mode()
    if mode is not None:
        logger.debug(f"Display Mode:         {mode} (error flag: {err_flag})")

    logger.debug("=" * 66)


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


def configure_dlpc900_for_video_pattern(dlpc, target_hz=60):
    logger.info(
        f"[+] Configuring DLPC900 for 1920x1080 @ {target_hz}Hz Video Pattern Mode ({BITPLANES} bit-planes)..."
    )
    logger.debug("Following TI documentation sequence (DLPU018J Section 5.1)...")

    # Step 1: Stop any existing pattern playback
    dlpc.start_pattern_display(0)
    time.sleep(0.2)

    # Step 2: Configure LEDs
    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    # Step 3: Enter Video Mode (0) FIRST with DisplayPort source
    # Per DLPU018J p.56: "Must first change to Video Mode (0) with desired source enabled"
    logger.debug("  - Entering Video Mode (0) with DisplayPort source...")
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)  # DisplayPort
    dlpc.toggle_dual_pixel_mode(True)

    # CRITICAL FIX: Explicitly tell the DLPC900 to use the full 1920x1080 active area.
    # Otherwise, it might remember a previous 512x512 crop from Flash and truncate patterns!
    logger.debug("  - Forcing Input Display Resolution to 1920x1080...")
    dlpc.set_input_display_resolution(0, 0, 1920, 1080)

    dlpc.apply_block_lock_workaround()

    # Step 4: Wait for sync lock (REQUIRED before mode 2 transition)
    logger.info("[+] Waiting for external source sync lock...")
    if wait_for_external_lock(dlpc, timeout_s=4.0):
        logger.info("[+] External source lock acquired. Ready for Video Pattern Mode.")
    else:
        logger.warning("[WARNING] External source lock not reported!")
        logger.warning(
            "[WARNING] Video Pattern Mode transition may fail without sync lock."
        )

    # Step 5: Set display mode to Video Pattern Mode (0x02)
    # Per DLPU018J p.56: "Takes approximately 300ms to complete the transition"
    logger.debug("  - Switching to Video Pattern Mode (0x02)...")
    dlpc.set_display_mode(0x02)

    # CRITICAL: Wait 300ms for mode transition as per documentation
    logger.debug("  - Waiting 300ms for mode transition (per TI spec)...")
    time.sleep(0.3)

    dlpc.apply_block_lock_workaround()

    # Additional settling time
    time.sleep(0.1)

    # Step 6: Verify we're actually in mode 2
    mode, _ = dlpc.get_display_mode()
    logger.debug(f"  - Display mode readback: {mode} (expected: 2)")

    # Step 7: Define pattern LUT (bit-plane extraction)
    entries, exposure_us = build_lut_entries(target_hz)
    logger.info(
        f"[+] LUT: {BITPLANES} entries, exposure={exposure_us}us, binary rate={BITPLANES * target_hz} Hz"
    )
    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(BITPLANES, repeat=True)

    # Step 8: Start pattern sequencer
    logger.info("[+] Starting pattern sequencer...")
    dlpc.start_pattern_display(2)
    time.sleep(0.2)

    # Verify mode stuck
    mode, _ = dlpc.get_display_mode()
    if mode != 2:
        logger.warning(f"[WARNING] Mode readback shows {mode}, not 2! Retrying...")
        dlpc.set_display_mode(0x02)
        time.sleep(0.3)
        dlpc.apply_block_lock_workaround()
        dlpc.start_pattern_display(2)
        time.sleep(0.2)
        mode, _ = dlpc.get_display_mode()
        logger.debug(f"  - After retry, mode readback: {mode}")


def verify_runtime_state(dlpc):
    ms = dlpc.get_main_status() or {}
    dd = dlpc.get_display_dimensions() or {}
    mode, _ = dlpc.get_display_mode()

    checks = {
        "display_mode_is_video_pattern": mode == 2,
        "sequencer_running": bool(ms.get("sequencer_running", False)),
    }

    logger.debug("Verification:")
    for name, ok in checks.items():
        logger.debug(f"  {name:30} {'PASS' if ok else 'FAIL'}")

    all_ok = all(checks.values())
    if not all_ok:
        logger.warning("[WARNING] Runtime verification checks failed!")
        logger.warning(
            "           Video Pattern Mode (2) not active or sequencer not running."
        )
        logger.warning(
            "           Check DisplayPort sync lock and mode transition timing."
        )
    else:
        logger.info(
            "[OK] Runtime verification passed (mode=VideoPattern, sequencer running)."
        )
    return all_ok


def run():
    parser = argparse.ArgumentParser(description="DLPC900 1080p Video Pattern Runtime")
    parser.add_argument(
        "--hz", type=int, default=60, help="Target Hz (60 or 120, experimental)"
    )
    parser.add_argument("--monitor", type=int, default=0, help="GLFW monitor index")
    parser.add_argument(
        "--test-checkerboard", action="store_true", help="Display static checkerboard"
    )
    parser.add_argument(
        "--test-ordering", action="store_true", help="Display bit-ordering diagnostic"
    )
    parser.add_argument(
        "--test-numbered",
        action="store_true",
        help="Display numbered region diagnostic",
    )
    parser.add_argument(
        "--test-single-pixel",
        action="store_true",
        help="Display 1x1 single pixel checkerboard (Note: creates optical diffraction bands with lasers)",
    )
    parser.add_argument(
        "--test-2x2",
        action="store_true",
        help="Display 2x2 pixel checkerboard to verify 1:1 mapping vs optical diffraction",
    )
    parser.add_argument(
        "--test-lines", action="store_true", help="Display alternating 1-pixel lines"
    )
    parser.add_argument(
        "--test-colors",
        action="store_true",
        help="Display sequence of pure RGB channels",
    )
    parser.add_argument(
        "--test-snake",
        action="store_true",
        help="Display high-speed randomly moving snake (tests 60fps dynamic refresh and triggers)",
    )
    parser.add_argument(
        "--test-gradient",
        action="store_true",
        help="Display temporal duty-cycle gradient",
    )
    parser.add_argument(
        "--trigger", action="store_true", help="Software Trigger Mode (Approach A)"
    )
    parser.add_argument(
        "--runtime-seconds",
        type=int,
        default=60,
        help="Runtime for diagnostic patterns",
    )
    parser.add_argument(
        "--wake-dp", action="store_true", help="Wake DP receiver in main.py"
    )
    parser.add_argument(
        "--capture",
        type=str,
        help="Save the generated packed frames to an mp4 video (e.g. test.mp4)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose diagnostic logging"
    )
    args = parser.parse_args()

    # Configure centralized logger
    setup_logger(args.verbose)

    if args.hz not in (60, 120):
        logger.error(f"Unsupported Hz: {args.hz}. Only 60Hz and 120Hz are supported.")
        raise SystemExit(f"Unsupported Hz: {args.hz}")

    # Allow configuration of TARGET_HZ
    target_hz = args.hz

    dlpc = None
    engine = None
    try:
        logger.info("[+] Initializing DLPC900...")
        dlpc = DLPC900()

        if args.wake_dp:
            logger.info("[+] Waking up DisplayPort receiver...")
            dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        configure_dlpc900_for_video_pattern(dlpc, target_hz)

        log_board_snapshot(dlpc, "POST-CONFIG (before GL stream)")

        from pattern_engine import PatternEngine

        engine = PatternEngine(monitor_index=args.monitor, fps=target_hz)

        logger.info(f"[+] Holding output for {args.runtime_seconds} seconds...")

        if args.trigger:
            logger.info("[+] Software Trigger Mode (Approach A) Active.")
            logger.info(
                "    Press spacebar to trigger 1 frame of pattern sequence, or ESC to exit."
            )

            # Start with black
            black_patterns = engine.generate_solid(0)
            black_frame = engine.pack_patterns(black_patterns)

            # The pattern to trigger
            if args.test_checkerboard:
                trig_patterns = engine.generate_checkerboard()
            elif args.test_numbered:
                from debug_scripts.debug_numbered_regions import generate_numbered_regions

                numbered_rgb = generate_numbered_regions(
                    1920, 1080, grid_cols=6, grid_rows=4
                )
                trig_patterns = engine.rgb_to_binary_patterns(numbered_rgb)
            elif args.test_single_pixel:
                trig_patterns = engine.generate_checkerboard(block_size=1)
            elif args.test_2x2:
                trig_patterns = engine.generate_checkerboard(block_size=2)
            elif args.test_lines:
                trig_patterns = engine.generate_lines()
            elif args.test_colors:
                trig_patterns = engine.rgb_to_binary_patterns(generate_solid_color(0))
            elif args.test_gradient:
                trig_patterns = engine.generate_gradient()
            else:
                trig_patterns = engine.generate_checkerboard()

            trig_frame = engine.pack_patterns(trig_patterns)

            end_t = time.time() + args.runtime_seconds
            triggered = False
            while time.time() < end_t and not engine.should_close():
                if engine.check_trigger_key():
                    logger.info("[!] Triggering sequence...")
                    engine.display_frame(trig_frame)
                    triggered = True
                else:
                    engine.display_frame(black_frame)

        else:
            # Generate initial frame based on test mode
            if args.test_ordering:
                logger.info("[+] Starting Diagnostic Mode: Bit Ordering Sweep...")
                patterns = engine.generate_ordering_diagnostic_patterns(1920, 1080)
            elif args.test_numbered:
                logger.info(
                    "[+] Starting Diagnostic Mode: Numbered Regions (6x4 grid)..."
                )
                from debug_scripts.debug_numbered_regions import generate_numbered_regions

                numbered_rgb = generate_numbered_regions(
                    1920, 1080, grid_cols=6, grid_rows=4
                )
                patterns = engine.rgb_to_binary_patterns(numbered_rgb)
            elif args.test_single_pixel:
                logger.info("[+] Starting Diagnostic Mode: 1x1 Single Pixel...")
                patterns = engine.generate_checkerboard(block_size=1)
            elif args.test_2x2:
                logger.info("[+] Starting Diagnostic Mode: 2x2 Checkerboard...")
                patterns = engine.generate_checkerboard(block_size=2)
            elif args.test_lines:
                logger.info("[+] Starting Diagnostic Mode: 1-pixel Lines...")
                patterns = engine.generate_lines()
            elif args.test_colors:
                logger.info("[+] Starting Diagnostic Mode: Color Channels (R/G/B)...")
                patterns = engine.rgb_to_binary_patterns(generate_solid_color(0))
            elif args.test_snake:
                logger.info("[+] Starting Diagnostic Mode: 60FPS Snake...")
                # The snake generates a pre-packed frame directly
                patterns = None
            elif args.test_gradient:
                logger.info("[+] Starting Diagnostic Mode: Temporal Gradient...")
                patterns = engine.generate_gradient()
            else:
                logger.info("[+] Starting Diagnostic Mode: Static Checkerboard...")
                patterns = engine.generate_checkerboard()

            if patterns is not None:
                frame = engine.pack_patterns(patterns)
            else:
                frame = engine.generate_snake_frame()
                
            engine.display_frame(frame)

            time.sleep(1.0)
            log_board_snapshot(dlpc, "POST-FIRST-FRAME (after GL stream)")
            verify_runtime_state(dlpc)

            # Pre-generate frames for dynamic patterns to prevent stuttering in the render loop
            if args.test_colors:
                solid_r = engine.pack_patterns(
                    engine.rgb_to_binary_patterns(generate_solid_color(0))
                )
                solid_g = engine.pack_patterns(
                    engine.rgb_to_binary_patterns(generate_solid_color(1))
                )
                solid_b = engine.pack_patterns(
                    engine.rgb_to_binary_patterns(generate_solid_color(2))
                )
            elif args.test_snake:
                # We will generate this on the fly, but we need an initial frame
                frame = engine.generate_snake_frame()

            video_out = None
            if args.capture and cv2 is not None:
                logger.info(f"[+] Recording packed frames to {args.capture}")
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                video_out = cv2.VideoWriter(
                    args.capture, fourcc, target_hz, (1920, 1080), isColor=True
                )
            elif args.capture and cv2 is None:
                logger.warning(
                    "[WARNING] Cannot capture video, opencv-python is not installed."
                )

            # ALWAYS render in a loop to keep OpenGL / VSYNC / X11 alive
            end_t = time.time() + args.runtime_seconds
            while time.time() < end_t and not engine.should_close():
                if args.test_colors:
                    sec = int(time.time() * 2) % 3
                    if sec == 0:
                        frame = solid_r
                    elif sec == 1:
                        frame = solid_g
                    else:
                        frame = solid_b
                elif args.test_snake:
                    # Generate the next frame dynamically (~1ms execution time)
                    frame = engine.generate_snake_frame()

                # Re-display the frame to prevent X11 from blanking the unresponsive window
                engine.display_frame(frame)

                if video_out is not None:
                    # Convert RGB (OpenGL format) to BGR (OpenCV format)
                    bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    video_out.write(bgr_frame)

            if video_out is not None:
                video_out.release()
                logger.info(f"[+] Video saved to {args.capture}")

    except Exception as exc:
        logger.exception(f"[ERROR] Runtime failed: {exc}")
    finally:
        logger.info("[+] Cleaning up...")
        if dlpc is not None:
            dlpc.start_pattern_display(0)
            dlpc.set_display_mode(0x00)
            dlpc.apply_block_lock_workaround()
        if engine is not None:
            engine.cleanup()


if __name__ == "__main__":
    run()
