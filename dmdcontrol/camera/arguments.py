"""Shared camera CLI argument groups."""

from __future__ import annotations

import argparse


def add_camera_performance_arguments(parser: argparse.ArgumentParser) -> None:
    """Add explicit DVXplorer sensitivity, readout, and global-hold controls."""

    parser.add_argument(
        "--bias-sensitivity",
        default="default",
        choices=["default", "verylow", "low", "high", "veryhigh"],
        help="DVXplorer contrast sensitivity preset; default leaves camera thresholds unchanged.",
    )
    parser.add_argument(
        "--efps",
        default="default",
        choices=[
            "default",
            "variable",
            "variable_5000",
            "constant_1000",
            "constant_100",
        ],
        help="DVXplorer readout mode; default leaves the camera setting unchanged.",
    )
    parser.add_argument(
        "--camera-global-hold",
        default="default",
        choices=["default", "on", "off"],
        help=(
            "DVXplorer global-hold policy. Default preserves the camera setting; "
            "use off only for a controlled LED/laser tracking comparison."
        ),
    )
