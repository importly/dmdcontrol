import os
import cv2
import numpy as np
import argparse

from debug_render import (
    generate_checkerboard,
    generate_lines,
    generate_solid,
    generate_gradient,
)
from debug_numbered_regions import generate_numbered_regions


def rgb_to_binary_patterns(rgb_array):
    """Extract 24 bit-planes from RGB in the exact order the DLPC900 Video Pattern Mode processes them."""
    patterns = []
    # 1. Green channel: bits 0-7
    for bit in range(8):
        patterns.append((rgb_array[:, :, 1] >> bit) & 1)
    # 2. Red channel: bits 8-15
    for bit in range(8):
        patterns.append((rgb_array[:, :, 0] >> bit) & 1)
    # 3. Blue channel: bits 16-23
    for bit in range(8):
        patterns.append((rgb_array[:, :, 2] >> bit) & 1)
    return patterns


def create_simulation_video(
    pattern_name, patterns, output_filename, fps=30, hold_seconds=0.5
):
    height, width = patterns[0].shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_filename, fourcc, fps, (width, height))

    frames_per_bit = int(fps * hold_seconds)

    for i, bit_img in enumerate(patterns):
        # Convert 0/1 binary matrix to 0/255 grayscale
        frame_gray = bit_img * 255

        # Convert to BGR so we can draw colored text on it
        frame_bgr = cv2.cvtColor(frame_gray, cv2.COLOR_GRAY2BGR)

        # Determine color channel name for the overlay
        if i < 8:
            channel = "GREEN"
            bit_idx = i
            color = (0, 255, 0)  # BGR
        elif i < 16:
            channel = "RED"
            bit_idx = i - 8
            color = (0, 0, 255)  # BGR
        else:
            channel = "BLUE"
            bit_idx = i - 16
            color = (255, 0, 0)  # BGR

        text = f"Frame {i + 1}/24 | {channel} Channel | Bit {bit_idx}"

        # Add a black background box for text readability
        cv2.rectangle(frame_bgr, (10, 10), (850, 70), (0, 0, 0), -1)
        # Draw the text overlay
        cv2.putText(frame_bgr, text, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 3)

        # Write the frame repeatedly to stretch time
        for _ in range(frames_per_bit):
            out.write(frame_bgr)

    out.release()
    print(f"Saved DMD slow-motion simulation to {output_filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Simulate DMD high-speed flashing in slow motion"
    )
    parser.add_argument(
        "--pattern",
        choices=["numbered", "gradient", "checkerboard", "lines", "2x2"],
        required=True,
    )
    args = parser.parse_args()

    width, height = 1920, 1080

    if args.pattern == "numbered":
        rgb = generate_numbered_regions(width, height, grid_cols=6, grid_rows=4)
        patterns = rgb_to_binary_patterns(rgb)
    elif args.pattern == "gradient":
        patterns = generate_gradient(width, height)
    elif args.pattern == "checkerboard":
        patterns = generate_checkerboard(width, height, block_size=32)
    elif args.pattern == "2x2":
        patterns = generate_checkerboard(width, height, block_size=2)
    elif args.pattern == "lines":
        patterns = generate_lines(width, height)

    out_dir = "simulations"
    os.makedirs(out_dir, exist_ok=True)

    out_file = os.path.join(out_dir, f"dmd_simulation_{args.pattern}.mp4")
    create_simulation_video(args.pattern, patterns, out_file, fps=30, hold_seconds=0.75)
