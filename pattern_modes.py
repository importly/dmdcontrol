"""Pattern mode registry. Maps --test name -> (label, builder).

Each builder takes the PatternEngine and returns (patterns_or_None, dynamic_kind).
- patterns: passed to engine.pack_patterns(); None for dynamic modes that generate frames directly.
- dynamic_kind: None for static; "snake", "clock", "colors" for dynamic frame providers.
"""

import numpy as np


def _solid_color(color_idx, width=1920, height=1080):
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, color_idx] = 255
    return img


def _numbered(engine):
    from debug_scripts.debug_numbered_regions import generate_numbered_regions
    rgb = generate_numbered_regions(1920, 1080, grid_cols=6, grid_rows=4)
    return engine.rgb_to_binary_patterns(rgb), None


PATTERN_MODES = {
    #                 label                                   pattern generator          dynamic or not
    "checkerboard":  ("Static Checkerboard",       lambda e: (e.generate_checkerboard(), None)),
    "ordering":      ("Bit Ordering Sweep",        lambda e: (e.generate_ordering_diagnostic_patterns(1920, 1080), None)),
    "numbered":      ("Numbered Regions (6x4 grid)", _numbered),
    "single-pixel":  ("1x1 Single Pixel",          lambda e: (e.generate_checkerboard(block_size=1), None)),
    "2x2":           ("2x2 Checkerboard",          lambda e: (e.generate_checkerboard(block_size=2), None)),
    "lines":         ("1-pixel Lines",             lambda e: (e.generate_lines(), None)),
    "colors":        ("Color Channels (R/G/B)",    lambda e: (e.rgb_to_binary_patterns(_solid_color(0)), "colors")),
    "snake":         ("60FPS Snake",               lambda e: (None, "snake")),
    "clock":         ("Microsecond Clock",         lambda e: (None, "clock")),
    "gradient":      ("Temporal Gradient",         lambda e: (e.generate_gradient(), None)),
    "kernel":        ("3x3 Kernel Variations (512 patterns)", lambda e: (None, "kernel")),
}

PATTERN_NAMES = list(PATTERN_MODES.keys())


def build_patterns(engine, mode):
    """Returns (label, patterns_or_None, dynamic_kind) for the given mode name."""
    label, builder = PATTERN_MODES[mode]
    patterns, dynamic_kind = builder(engine)
    return label, patterns, dynamic_kind
