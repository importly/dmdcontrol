from __future__ import annotations

import argparse

from dmdcontrol.support.constants import (
    TRIGGER_OUT_RISING_DELAY_MAX_US,
    TRIGGER_OUT_RISING_DELAY_MIN_US,
)


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be positive") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def nonnegative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be non-negative") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return number


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be positive") from exc
    if number <= 0.0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def unit_interval_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be in the interval (0, 1]") from exc
    if number <= 0.0 or number > 1.0:
        raise argparse.ArgumentTypeError("value must be in the interval (0, 1]")
    return number


def count_slots_per_frame(value: str) -> int | None:
    if value.strip().lower() == "auto":
        return None
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "count slots per frame must be a positive integer or 'auto'") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError(
            "count slots per frame must be a positive integer or 'auto'")
    return number


def trigger_out_rising_delay_us(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "trigger rising delay must be an integer microsecond value") from exc
    if number < TRIGGER_OUT_RISING_DELAY_MIN_US or number > TRIGGER_OUT_RISING_DELAY_MAX_US:
        raise argparse.ArgumentTypeError(
            "trigger rising delay must be between "
            f"{TRIGGER_OUT_RISING_DELAY_MIN_US} and {TRIGGER_OUT_RISING_DELAY_MAX_US} us")
    return number
