"""Paired dual-DMD runtime for one 3840x1080 OpenGL swap loop."""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass

from config import DEFAULT_SEQUENCE_UTILIZATION
from dlpc_lifecycle import (
    build_lut_entries,
    load_pattern_sequence,
    prepare_dlpc900_for_video_pattern,
    start_loaded_pattern_sequences,
)
from dmd_config import DmdMapping, resolve_dmd_mapping
from logger import logger, setup_logger
from paired_pattern_engine import (
    DMD_HEIGHT,
    DMD_WIDTH,
    OFFSET_A,
    OFFSET_B,
    PAIR_HEIGHT,
    PAIR_TESTS,
    PAIR_WIDTH,
    STATIC_PAIR_TESTS,
    make_pair_frame_provider,
)


@dataclass(frozen=True)
class PairConfig:
    dmd_a: DmdMapping
    dmd_b: DmdMapping
    desktop_width: int = PAIR_WIDTH
    desktop_height: int = PAIR_HEIGHT
    offset_b: tuple[int, int] = OFFSET_B
    offset_a: tuple[int, int] = OFFSET_A
    target_hz: int = 60


class _DryRunDLPC:
    def get_display_dimensions(self):
        return None


def resolve_pair_config(config_path=None, target_hz=None):
    dmd_a = resolve_dmd_mapping("A", config_path)
    dmd_b = resolve_dmd_mapping("B", config_path)
    for mapping in (dmd_a, dmd_b):
        if not mapping.xrandr_output:
            raise ValueError(
                f"DMD {mapping.name} must define xrandr_output for paired runs."
            )
        if not mapping.usb_id_path:
            raise ValueError(
                f"DMD {mapping.name} must define usb_id_path for paired runs."
            )

    configured_hz = {
        hz for hz in (dmd_a.target_hz, dmd_b.target_hz) if hz is not None
    }
    if len(configured_hz) > 1:
        raise ValueError(
            f"Paired DMD target_hz values must match, got {sorted(configured_hz)}"
        )
    resolved_hz = int(target_hz or next(iter(configured_hz), 60))
    return PairConfig(dmd_a=dmd_a, dmd_b=dmd_b, target_hz=resolved_hz)


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Dual DLPC900 paired Video Pattern Mode runtime"
    )
    parser.add_argument("--hz", type=int, default=None, help="Target Hz, default from dmd_devices.json or 60")
    parser.add_argument("--dmd-config", default=None, help="Path to DMD mapping config")
    parser.add_argument("--test", choices=PAIR_TESTS, default="checkerboard")
    parser.add_argument(
        "--test-a",
        choices=STATIC_PAIR_TESTS,
        default=None,
        help="Static pattern for DMD A when --test is a static paired mode",
    )
    parser.add_argument(
        "--test-b",
        choices=STATIC_PAIR_TESTS,
        default=None,
        help="Static pattern for DMD B when --test is a static paired mode",
    )
    parser.add_argument("--runtime-seconds", type=int, default=60)
    parser.add_argument("--wake-dp", action="store_true", help="Wake both DP receivers in main_pair.py")
    parser.add_argument(
        "--dual-pixel",
        action="store_true",
        help="Force dual-pixel P1-P2 mode on both DLPC900 controllers",
    )
    parser.add_argument(
        "--seq-utilization",
        type=float,
        default=DEFAULT_SEQUENCE_UTILIZATION,
        help="Fraction of safe frame budget allocated to LUT exposure timing",
    )
    parser.add_argument(
        "--trig2-frame-zero",
        action="store_true",
        help="Emit TRIG_OUT_2 only for bitplane/frame-zero anchor entries",
    )
    parser.add_argument(
        "--dry-run-timing",
        action="store_true",
        help="Print paired mapping and LUT timing without importing OpenGL or USB hardware",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0)
    return parser


def _dry_run_timing(args, pair_config):
    entries, timing = build_lut_entries(
        _DryRunDLPC(),
        pair_config.target_hz,
        sequence_utilization=args.seq_utilization,
        trig2_frame_zero=args.trig2_frame_zero,
    )
    logger.info("[DRY RUN] Hardware was not opened. OpenGL and USB modules were not imported.")
    logger.info(
        f"[DRY RUN] X layout: {pair_config.desktop_width}x{pair_config.desktop_height}; "
        f"B {pair_config.dmd_b.xrandr_output} at +{pair_config.offset_b[0]}+{pair_config.offset_b[1]}, "
        f"A {pair_config.dmd_a.xrandr_output} at +{pair_config.offset_a[0]}+{pair_config.offset_a[1]}."
    )
    logger.info(
        f"[DRY RUN] USB: A id_path={pair_config.dmd_a.usb_id_path}, "
        f"B id_path={pair_config.dmd_b.usb_id_path}."
    )
    if args.test in STATIC_PAIR_TESTS:
        logger.info(
            f"[DRY RUN] Pair content: test={args.test}, test_a={args.test_a or args.test}, "
            f"test_b={args.test_b or args.test}."
        )
    else:
        logger.info(
            f"[DRY RUN] Pair content: dynamic test={args.test}, one shared frame index/timebase."
        )
    logger.info(
        f"[DRY RUN] Pattern LUT: {len(entries)} entries, exposure={timing['exposure_us']}us, "
        f"dark={timing['dark_us']}us, sequence={timing['total_sequence_us']:.1f}/"
        f"{timing['usable_frame_period_us']:.1f}us usable, "
        f"effective VSYNC={timing['effective_frame_hz']:.3f}Hz."
    )
    logger.info(
        f"[DRY RUN] TRIG_OUT_2 mode: {timing['trig2_mode']}; expected pulses/s="
        f"{timing['effective_frame_hz'] if args.trig2_frame_zero else timing['effective_binary_rate_hz']:.1f}."
    )


def _run_pair_render_loop(dlpc_a, dlpc_b, engine, provider, args):
    end_t = None if args.runtime_seconds <= 0 else time.time() + args.runtime_seconds
    while (end_t is None or time.time() < end_t) and not engine.should_close():
        frame_a, frame_b = provider.next_pair()
        engine.display_pair(frame_a, frame_b)


def _start_pair_pump(engine, provider):
    pump_event = threading.Event()
    pump_ready = threading.Event()
    frame_a, frame_b = provider.initial_pair()

    def _continuous_pump():
        engine.make_context_current()
        pump_ready.set()
        try:
            while pump_event.is_set():
                engine.display_pair(frame_a, frame_b)
        finally:
            engine.release_context()

    engine.release_context()
    pump_event.set()
    thread = threading.Thread(target=_continuous_pump, daemon=True)
    thread.start()
    pump_ready.wait(timeout=1.0)
    time.sleep(0.1)
    return pump_event, thread


def _stop_pair_pump(engine, pump_event, pump_thread):
    if pump_event is not None:
        pump_event.clear()
    if pump_thread is not None:
        pump_thread.join(timeout=1.0)
    engine.make_context_current()


def main(argv=None):
    args = _build_parser().parse_args(argv)
    setup_logger(verbosity=args.verbose)
    pair_config = resolve_pair_config(args.dmd_config, target_hz=args.hz)

    if args.test in STATIC_PAIR_TESTS:
        provider = make_pair_frame_provider(
            args.test,
            test_a=args.test_a,
            test_b=args.test_b,
            width=DMD_WIDTH,
            height=DMD_HEIGHT,
        )
    else:
        if args.test_a or args.test_b:
            raise SystemExit("--test-a/--test-b are only valid for static paired tests")
        provider = make_pair_frame_provider(args.test, width=DMD_WIDTH, height=DMD_HEIGHT)

    if args.dry_run_timing:
        _dry_run_timing(args, pair_config)
        return 0

    from dlpc900_hid import DLPC900
    from paired_pattern_engine import PairedPatternEngine

    logger.info(
        f"[+] Paired DMD layout: B {pair_config.dmd_b.xrandr_output} left +0+0, "
        f"A {pair_config.dmd_a.xrandr_output} right +{DMD_WIDTH}+0"
    )
    engine = None
    dlpc_a = None
    dlpc_b = None
    pump_event = None
    pump_thread = None
    try:
        engine = PairedPatternEngine(fps=pair_config.target_hz)
        dlpc_a = DLPC900(
            usb_id_path=pair_config.dmd_a.usb_id_path,
            usb_devpath_contains=pair_config.dmd_a.usb_devpath_contains,
        )
        dlpc_b = DLPC900(
            usb_id_path=pair_config.dmd_b.usb_id_path,
            usb_devpath_contains=pair_config.dmd_b.usb_devpath_contains,
        )

        if args.wake_dp:
            for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
                logger.info(f"[+] Waking DisplayPort receiver for DMD {label}...")
                dlpc.send_packet(0x1A01, bytes([2]))
            time.sleep(1.0)

        logger.info("[+] Starting paired continuous GL pump before DLPC preparation...")
        pump_event, pump_thread = _start_pair_pump(engine, provider)

        logger.info("[+] Preparing DMD A controller without starting sequencer...")
        state_a = prepare_dlpc900_for_video_pattern(
            dlpc_a,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
        )
        logger.info("[+] Preparing DMD B controller without starting sequencer...")
        state_b = prepare_dlpc900_for_video_pattern(
            dlpc_b,
            pair_config.target_hz,
            dual_pixel=args.dual_pixel,
            sequence_utilization=args.seq_utilization,
            trig2_frame_zero=args.trig2_frame_zero,
        )

        logger.info("[+] Loading paired pattern LUTs without starting sequencers...")
        load_pattern_sequence(dlpc_a, state_a["entries"])
        load_pattern_sequence(dlpc_b, state_b["entries"])

        logger.info("[+] Starting both DLPC900 sequencers from paired software barrier...")
        start_loaded_pattern_sequences(dlpc_a, dlpc_b, verify=True)
        logger.info("[SCOPE] Compare TRIG_OUT_2_A and TRIG_OUT_2_B for start skew and drift.")

        _stop_pair_pump(engine, pump_event, pump_thread)
        pump_event = None
        pump_thread = None

        first_a, first_b = provider.initial_pair()
        engine.display_pair(first_a, first_b)
        _run_pair_render_loop(dlpc_a, dlpc_b, engine, provider, args)
        return 0
    finally:
        if engine is not None and pump_event is not None:
            _stop_pair_pump(engine, pump_event, pump_thread)
        for label, dlpc in (("A", dlpc_a), ("B", dlpc_b)):
            if dlpc is None:
                continue
            try:
                logger.info(f"[-] Stopping DMD {label} pattern display...")
                dlpc.start_pattern_display(0)
                dlpc.set_display_mode(0x00)
                dlpc.apply_block_lock_workaround()
            except Exception as cleanup_exc:
                logger.warning(f"DMD {label} cleanup warning: {cleanup_exc}")
        if engine is not None:
            engine.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.exception(f"[ERROR] {exc}")
        raise SystemExit(1)
