#!/usr/bin/env python3
"""
Generate numbered region diagnostic patterns to visualize geometry distortion.
Divides the display into a grid with numbered regions to see how they map to the DMD.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from dmdcontrol.patterns.numbered_regions import generate_numbered_regions


def generate_crop_visualization(width, height, crop_x, crop_y, crop_w, crop_h):
    """
    Generate a pattern showing what the hardware crop extracts.

    Args:
        width, height: Full frame size (1920x1080)
        crop_x, crop_y, crop_w, crop_h: Crop region parameters

    Returns:
        RGB numpy array with crop region highlighted
    """
    img = Image.new("RGB", (width, height), color=(50, 50, 50))
    draw = ImageDraw.Draw(img)

    # Draw the crop region in bright color
    draw.rectangle(
        [crop_x,
         crop_y,
         crop_x + crop_w,
         crop_y + crop_h],
        fill=(200,
              200,
              0),
        outline="red",
        width=5,
    )

    # Add crosshairs at center
    center_x = crop_x + crop_w // 2
    center_y = crop_y + crop_h // 2
    draw.line([(center_x - 50, center_y), (center_x + 50, center_y)], fill="red", width=3)
    draw.line([(center_x, center_y - 50), (center_x, center_y + 50)], fill="red", width=3)

    # Add text labels
    try:
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        font = ImageFont.load_default()

    label = f"Crop: {crop_w}x{crop_h} @ ({crop_x},{crop_y})"
    draw.text((crop_x + 10, crop_y + 10), label, fill="white", font=font)

    return np.array(img)


def save_numbered_diagnostics():
    """Generate and save numbered region diagnostic images."""
    width, height = 1920, 1080
    out_dir = "diagnostic_images"
    os.makedirs(out_dir, exist_ok=True)

    print(f"\nGenerating numbered region diagnostics ({width}x{height})...")

    # Full frame with 6x4 grid (24 numbered regions)
    print("  - Creating 6x4 numbered grid...")
    numbered_pattern = generate_numbered_regions(width, height, grid_cols=6, grid_rows=4)
    img_full = Image.fromarray(numbered_pattern)
    full_path = os.path.join(out_dir, "diagnostic_numbered_full.png")
    img_full.save(full_path)
    print(f"    Saved: {full_path}")

    # Show crop region
    crop_x, crop_y, crop_w, crop_h = 704, 284, 512, 512
    print(f"  - Creating crop visualization ({crop_w}x{crop_h} @ {crop_x},{crop_y})...")
    crop_viz = generate_crop_visualization(width, height, crop_x, crop_y, crop_w, crop_h)
    img_crop_viz = Image.fromarray(crop_viz)
    crop_viz_path = os.path.join(out_dir, "diagnostic_crop_visualization.png")
    img_crop_viz.save(crop_viz_path)
    print(f"    Saved: {crop_viz_path}")

    # Extract actual crop for comparison
    print("  - Extracting crop region from numbered pattern...")
    cropped_numbered = numbered_pattern[crop_y:crop_y + crop_h, crop_x:crop_x + crop_w]
    img_cropped = Image.fromarray(cropped_numbered)
    crop_path = os.path.join(out_dir, "diagnostic_numbered_crop.png")
    img_cropped.save(crop_path)
    print(f"    Saved: {crop_path}")

    print("\nDiagnostic images generated:")
    print("  1. diagnostic_numbered_full.png - Full 1920x1080 with numbered regions")
    print("  2. diagnostic_crop_visualization.png - Shows where hardware crop is positioned")
    print("  3. diagnostic_numbered_crop.png - What the 512x512 crop should extract")


if __name__ == "__main__":
    save_numbered_diagnostics()
