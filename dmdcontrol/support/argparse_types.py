from __future__ import annotations

import argparse


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


def numbers_bitplane_order(value: str) -> list[int]:
    try:
        order = [int(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("numbers bitplane order must be decimal indexes") from exc
    if not order:
        raise argparse.ArgumentTypeError("numbers bitplane order must not be empty")
    if any(index < 0 for index in order):
        raise argparse.ArgumentTypeError("numbers bitplane order indexes must be non-negative")
    return order
