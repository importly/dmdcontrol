"""Pattern generation and rendering engines for dmdcontrol."""
from .paired import (
    FramePair,
    PairFrameProvider,
    RGBFrame,
    PairedPatternEngine,
    pack_sequence_frames, 
    pack_static_frames,
    count_lut_entries_per_frame, 
    generate_dot_frame,
    as_frame_pair,
    _decimal_number_display_masks,
)