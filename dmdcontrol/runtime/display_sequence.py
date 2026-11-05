"""What the paired DMDs show, and bringing both DLPC900s up to show it.

A sequence is one cycle of FramePairs (one per VSYNC, repeated for the run) plus the LUT each
controller runs. A exposes once per VSYNC with TRIG_OUT_2 on every entry; that is the camera
trigger. B holds its pattern through the whole VSYNC (no clear) and only triggers on entry 0.

Bring-up order per controller: Video Mode on DisplayPort -> stable lock -> Video Pattern Mode ->
stable lock -> trigger outputs. Then the LUTs are loaded and both sequencers start together.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from dmdcontrol.dmd import (
    ensure_video_pattern_mode,
    wait_for_external_lock,
    wait_for_sequencer_running,
    wait_for_stable_external_lock,
)
from dmdcontrol.patterns import (
    Frame,
    FramePair,
    PairFrameProvider,
    RGBFrame,
    checkerboard_frame,
    generate_dot_frame,
    pack_count_sequence_frames,
)
from dmdcontrol.patterns.gpu import BLANK, MaskPattern
from dmdcontrol.utils import CONFIG

if TYPE_CHECKING:
    from dmdcontrol.dmd import DLPC900

logger = logging.getLogger('DisplaySequence')

DMD = CONFIG.DMD
RUN = CONFIG.Run


@dataclass(frozen=True)
class LutEntry:
    """One DLPC900 pattern LUT entry (DLPU018J 0x1A34)."""

    pattern_index: int
    exposure_us: int
    dark_us: int
    bit_position: int
    clear_after: bool
    trig2_disabled: bool
    wait_for_trigger: bool
    bit_depth: int = 1
    led_select: int = 7
    image_pattern_index: int = 0


def build_lut_entries(hold_last: bool = False, trigger_first_only: bool = False) -> tuple[LutEntry, ...]:
    """As many DMD.exposure_us entries as fit in one VSYNC, on bitplanes 0, 1, ...

    hold_last keeps the last pattern on for the rest of the VSYNC instead of clearing it;
    trigger_first_only fires TRIG_OUT_2 on entry 0 only.
    """
    exposure_us, dark_us = DMD.exposure_us, DMD.dark_time_us
    usable_us = (1e6 / DMD.target_hz - DMD.safe_margin_us) * DMD.frame_utilization
    count = min(DMD.bitplanes, int(usable_us // (exposure_us + dark_us)))
    if count < 1:
        raise ValueError(f'exposure_us {exposure_us} + dark_time_us {dark_us} does not fit in one VSYNC '
                         f'({usable_us:.0f} us usable)')
    return tuple(
        LutEntry(pattern_index=i, exposure_us=exposure_us, dark_us=dark_us, bit_position=i,
                 clear_after=not hold_last and i == count - 1,
                 trig2_disabled=trigger_first_only and i != 0,
                 wait_for_trigger=i == 0)
        for i in range(count))


class FrameCycle(PairFrameProvider):
    """frames[0] first, then each following frame, wrapping around."""

    def __init__(self, frames: tuple[FramePair, ...]):
        self.frames = frames
        self.index = 0

    def initial_pair(self) -> FramePair:
        self.index = 0
        return self.frames[0]

    def next_pair(self) -> FramePair:
        self.index = (self.index + 1) % len(self.frames)
        return self.frames[self.index]


@dataclass
class PairedDisplaySequence:
    """One cycle of frames (one per VSYNC, repeated) and the LUT each controller runs while they show."""

    frames: tuple[FramePair, ...]
    labels: tuple[str, ...]          # 'count:5', 'blank', ... parallel to frames
    startup_pair: FramePair          # held before the sequencers start and for the leader VSYNCs
    entries_a: tuple[LutEntry, ...]
    entries_b: tuple[LutEntry, ...]
    leader_vsyncs: int
    provider: FrameCycle = field(init=False)

    def __post_init__(self):
        self.provider = FrameCycle(self.frames)

    @property
    def leader_triggers(self) -> int:
        """TRIG_OUT_2 pulses A fires during the startup leader; the camera skips these."""
        return self.leader_vsyncs * sum(not entry.trig2_disabled for entry in self.entries_a)


def build_count_static_sequence() -> PairedDisplaySequence:
    """A: count, blank, count, blank, ... over Run.count_start..count_end. B: Run.test_b held."""
    start, end = RUN.Count.start, RUN.Count.end
    labels = [label for count in range(start, end + 1) for label in (f'count:{count}', 'blank')]
    return _paired_sequence(pack_count_sequence_frames(start, end, RUN.Count.number_size_px), _static_b(), labels)


def build_kernel_sequence(fm: np.ndarray, kernel: np.ndarray) -> PairedDisplaySequence:
    """One kernel pass over N samples: fm (N, h, w) on A, kernel (N, kh, kw) on B, or one (kh, kw) for all; +-1.

    Each operand pixel is a square of Run.Kernel.mirrors_per_px mirrors (nearest neighbour),
    centred on its DMD. Sample i shows fm[i] on A with kernel[i] on B, as four captures, each
    followed by a blank: every sample's (k+ fm+), then every (k+ fm-), (k- fm+), (k- fm-). So the
    content frames come in those four blocks of N, between a bright marker and a warm-up capture
    before them and a bright marker after, none of them used.
    """
    mirrors = CONFIG.Run.Kernel.mirrors_per_px
    shared = kernel.ndim == 2
    kernels = kernel[None] if shared else kernel
    if not shared and len(kernels) != len(fm):
        raise ValueError(f'{len(fm)} feature maps but {len(kernels)} kernels')
    a = {sign: [MaskPattern(_mirror_blocks(m * sign > 0, mirrors)) for m in fm] for sign in (1, -1)}
    b = {sign: [MaskPattern(_mirror_blocks(k * sign > 0, mirrors)) for k in kernels] for sign in (1, -1)}
    # all mirrors on at both ends, so find_semantic_frames can't be off by a whole capture when a pass's
    # first or last capture is dark; the warm-up takes the over-bright first capture after the leader
    bright = FramePair(a=MaskPattern(_mirror_blocks(np.ones(fm.shape[1:], bool), mirrors)),
                       b=MaskPattern(_mirror_blocks(np.ones(kernels.shape[1:], bool), mirrors)))
    frames = [bright, FramePair(a=BLANK, b=bright.b), FramePair(a=a[1][0], b=b[1][0]), FramePair(a=BLANK, b=b[1][0])]
    labels = ['marker', 'blank', 'warm-up', 'blank']
    for kernel_sign in (1, -1):
        for fm_sign in (1, -1):
            for index in range(len(fm)):
                b_pattern = b[kernel_sign][0 if shared else index]
                frames += [FramePair(a=a[fm_sign][index], b=b_pattern), FramePair(a=BLANK, b=b_pattern)]
                labels += [f'k{"+-"[kernel_sign < 0]} fm{"+-"[fm_sign < 0]}:{index}', 'blank']
    frames += [bright, FramePair(a=BLANK, b=bright.b)]
    labels += ['marker', 'blank']
    return _sequence(frames, labels, startup_pair=FramePair(a=BLANK, b=frames[0].b))


def _mirror_blocks(mask: np.ndarray, mirrors: int) -> np.ndarray:
    """Each mask pixel as a mirrors x mirrors square (nearest neighbour)."""
    return np.repeat(np.repeat(mask, mirrors, axis=0), mirrors, axis=1)


def _static_b() -> RGBFrame:
    if RUN.Count.test_b == 'checkerboard':
        return checkerboard_frame()
    return generate_dot_frame(x=RUN.Count.b_dot_x, y=RUN.Count.b_dot_y, radius=RUN.Count.b_dot_radius)


def _paired_sequence(frames_a, frame_b: Frame, labels: list[str]) -> PairedDisplaySequence:
    blank = np.zeros((DMD.height, DMD.width, 3), dtype=np.uint8)
    return _sequence([FramePair(a=frame_a, b=frame_b) for frame_a in frames_a], labels,
                     startup_pair=FramePair(a=blank, b=frame_b))


def _sequence(frames: list[FramePair], labels: list[str], startup_pair: FramePair) -> PairedDisplaySequence:
    return PairedDisplaySequence(
        frames=tuple(frames),
        labels=tuple(labels),
        startup_pair=startup_pair,
        entries_a=build_lut_entries(),
        entries_b=build_lut_entries(hold_last=True, trigger_first_only=True),
        leader_vsyncs=DMD.paired_startup_leader_vsyncs,
    )


# Controller bring-up

def prepare_pair_controllers(dlpc_a: DLPC900, dlpc_b: DLPC900) -> None:
    """Bring both controllers to Video Pattern Mode concurrently, without starting their sequencers."""
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='dlpc900-prepare') as pool:
        for future in [pool.submit(_prepare_controller, 'A', dlpc_a), pool.submit(_prepare_controller, 'B', dlpc_b)]:
            future.result()


def _prepare_controller(label: str, dlpc: DLPC900) -> None:
    logger.info('[DMD %s] Configuring for %sx%s @ %sHz Video Pattern Mode', label, DMD.width, DMD.height, DMD.target_hz)

    # Pattern Stop is NACKed outside Pattern Mode, so only stop if a pattern is running
    if dlpc.get_display_mode()[0] == 2:
        dlpc.start_pattern_display(0)
        time.sleep(0.2)

    dlpc.set_led_current(255, 255, 255)
    dlpc.set_led_enables(True, True, True, sequencer=True)

    # Video Mode (0) with the DisplayPort source has to come before Video Pattern Mode (2)
    dlpc.set_display_mode(0x00)
    dlpc.set_input_source(0, 1)
    dlpc.set_input_pixel_format(0)       # RGB888
    dlpc.set_data_channel_swap(0, 4)     # EVM ABC -> BAC on port 1
    dlpc.toggle_dual_pixel_mode(DMD.dual_pixel)
    dlpc.set_input_display_resolution(0, 0, DMD.width, DMD.height)  # else a stale flash crop
    dlpc.apply_block_lock_workaround()

    if not wait_for_external_lock(dlpc, timeout_s=4.0):
        raise RuntimeError(f'DMD {label}: no DisplayPort sync lock; Video Pattern Mode and triggers would be unreliable')
    if not wait_for_stable_external_lock(dlpc, timeout_s=3.0, stable_for_s=0.25, required_mode=0):
        logger.warning('[DMD %s] Video input not continuously stable for 3s; continuing', label)

    # Mode transition takes ~300 ms (DLPU018J p.56); TI's GUI waits 500 ms
    dlpc.set_display_mode(0x02)
    time.sleep(0.5)
    # Stop before park, otherwise the firmware latches abort bit 0x40
    dlpc.start_pattern_display(0)
    time.sleep(0.05)
    dlpc.apply_block_lock_workaround()
    time.sleep(0.1)
    if not ensure_video_pattern_mode(dlpc, retries=3, poll_timeout_s=1.5):
        raise RuntimeError(f'DMD {label}: did not enter Video Pattern Mode (triggers are off in Video Mode)')

    # The transition and park/unpark can reset the DP receiver: lock again before arming
    if not wait_for_external_lock(dlpc, timeout_s=6.0):
        logger.warning('[DMD %s] DisplayPort lock not regained in Video Pattern Mode; triggers may be unreliable', label)
    elif not wait_for_stable_external_lock(dlpc, timeout_s=2.0, stable_for_s=0.25, required_mode=2):
        logger.warning('[DMD %s] Video Pattern Mode input not continuously stable for 2s; continuing', label)

    # Non-inverted, rising <= falling, 20 us minimum pulse (DLPU018J Tables 2-118/2-120)
    rising_us = DMD.trigger_out.rising_delay_us
    dlpc.configure_trigger_out_1(polarity_high=True, rising_delay_us=0, falling_delay_us=20)
    dlpc.configure_trigger_out_2(polarity_high=True, rising_delay_us=rising_us,
                                 falling_delay_us=rising_us + DMD.trigger_out.pulse_width_us)

    # Arming before several VSYNCs in mode 2 causes forced-swap (0x08) and then abort (0x40)
    if not wait_for_stable_external_lock(dlpc, timeout_s=1.0, stable_for_s=max(0.2, 8.0 / DMD.target_hz), required_mode=2):
        logger.warning('[DMD %s] Final VSYNC input not continuously stable for 1s; continuing', label)
    logger.info('[DMD %s] Controller ready', label)


def load_pattern_sequence(dlpc: DLPC900, entries: tuple[LutEntry, ...]) -> None:
    dlpc.set_pattern_lut_definition(entries)
    dlpc.set_pattern_lut_config(len(entries), repeat=True)
    logger.info('LUT loaded: %d entr%s, exposure %d us, dark %d us', len(entries), 'y' if len(entries) == 1 else 'ies',
                entries[0].exposure_us, entries[0].dark_us)


def start_loaded_pattern_sequences(dlpc_a: DLPC900, dlpc_b: DLPC900) -> None:
    """Start both sequencers from two threads released together, to keep their skew small."""
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def start(label: str, dlpc: DLPC900) -> None:
        try:
            barrier.wait()
            dlpc.start_pattern_display(2)
        except Exception as exc:
            errors.append(f'{label}: {exc}')

    threads = [threading.Thread(target=start, args=(label, dlpc)) for label, dlpc in (('A', dlpc_a), ('B', dlpc_b))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise RuntimeError('Paired sequencer start failed: ' + '; '.join(errors))


def verify_started_pattern_sequence(dlpc: DLPC900, label: str = 'DLPC900') -> int | None:
    """Raise unless the controller is in Video Pattern Mode with its sequencer running; return the hardware status."""
    if not ensure_video_pattern_mode(dlpc, retries=2, poll_timeout_s=1.0):
        raise RuntimeError(f'{label} dropped out of Video Pattern Mode after sequencer start')
    if not wait_for_sequencer_running(dlpc, timeout_s=1.5):
        raise RuntimeError(f'{label} sequencer did not report running after start')
    hw = dlpc.get_hardware_status()
    if hw is not None and hw & 0x80:
        logger.warning('%s hardware status sequence-error bit set (hw=0x%02X)', label, hw)
    return hw
