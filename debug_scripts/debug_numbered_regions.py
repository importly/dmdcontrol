#!/usr/bin/env python3
"""
Generate numbered region diagnostic patterns to visualize geometry distortion.
Divides the display into a grid with numbered regions to see how they map to the DMD.
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def generate_numbered_regions(width, height, grid_cols=6, grid_rows=4):
    """
    Generate a diagnostic pattern with numbered regions.

    Args:
        width, height: Output dimensions (1920x1080)
        grid_cols, grid_rows: Grid division (default 6x4 = 24 regions)

    Returns:
        RGB numpy array with numbered regions
    """
    img = Image.new("RGB", (width, height), color="black")
    draw = ImageDraw.Draw(img)

    # Try to use a large font, fallback to default if not available
    try:
        font = ImageFont.truetype("arial.ttf", 80)
    except:
        font = ImageFont.load_default()

    cell_width = width // grid_cols
    cell_height = height // grid_rows

    # Colors to cycle through for visual distinction
    colors = [
        (255, 100, 100),  # Red
        (100, 255, 100),  # Green
        (100, 100, 255),  # Blue
        (255, 255, 100),  # Yellow
        (255, 100, 255),  # Magenta
        (100, 255, 255),  # Cyan
    ]

    region_num = 1
    for row in range(grid_rows):
        for col in range(grid_cols):
            x1 = col * cell_width
            y1 = row * cell_height
            x2 = x1 + cell_width
            y2 = y1 + cell_height

            # Alternate colors
            color = colors[(row + col) % len(colors)]

            # Draw filled rectangle
            draw.rectangle([x1, y1, x2, y2], fill=color, outline="white", width=3)

            # Draw region number in center
            text = str(region_num)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            text_x = x1 + (cell_width - text_width) // 2
            text_y = y1 + (cell_height - text_height) // 2

            # Draw text with black outline for visibility
            for offset_x in [-2, 0, 2]:
                for offset_y in [-2, 0, 2]:
                    draw.text(
                        (text_x + offset_x, text_y + offset_y),
                        text,
                        fill="black",
                        font=font,
                    )
            draw.text((text_x, text_y), text, fill="white", font=font)

            region_num += 1

    return np.array(img)


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
        [crop_x, crop_y, crop_x + crop_w, crop_y + crop_h],
        fill=(200, 200, 0),
        outline="red",
        width=5,
    )

    # Add crosshairs at center
    center_x = crop_x + crop_w // 2
    center_y = crop_y + crop_h // 2
    draw.line(
        [(center_x - 50, center_y), (center_x + 50, center_y)], fill="red", width=3
    )
    draw.line(
        [(center_x, center_y - 50), (center_x, center_y + 50)], fill="red", width=3
    )

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
    numbered_pattern = generate_numbered_regions(
        width, height, grid_cols=6, grid_rows=4
    )
    img_full = Image.fromarray(numbered_pattern)
    full_path = os.path.join(out_dir, "diagnostic_numbered_full.png")
    img_full.save(full_path)
    print(f"    Saved: {full_path}")

    # Show crop region
    crop_x, crop_y, crop_w, crop_h = 704, 284, 512, 512
    print(f"  - Creating crop visualization ({crop_w}x{crop_h} @ {crop_x},{crop_y})...")
    crop_viz = generate_crop_visualization(
        width, height, crop_x, crop_y, crop_w, crop_h
    )
    img_crop_viz = Image.fromarray(crop_viz)
    crop_viz_path = os.path.join(out_dir, "diagnostic_crop_visualization.png")
    img_crop_viz.save(crop_viz_path)
    print(f"    Saved: {crop_viz_path}")

    # Extract actual crop for comparison
    print("  - Extracting crop region from numbered pattern...")
    cropped_numbered = numbered_pattern[
        crop_y : crop_y + crop_h, crop_x : crop_x + crop_w
    ]
    img_cropped = Image.fromarray(cropped_numbered)
    crop_path = os.path.join(out_dir, "diagnostic_numbered_crop.png")
    img_cropped.save(crop_path)
    print(f"    Saved: {crop_path}")

    print("\nDiagnostic images generated:")
    print("  1. diagnostic_numbered_full.png - Full 1920x1080 with numbered regions")
    print(
        "  2. diagnostic_crop_visualization.png - Shows where hardware crop is positioned"
    )
    print("  3. diagnostic_numbered_crop.png - What the 512x512 crop should extract")


if __name__ == "__main__":
    save_numbered_diagnostics()
