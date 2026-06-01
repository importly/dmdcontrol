"""Numbered diagnostic region pattern generation."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def generate_numbered_regions(width, height, grid_cols=6, grid_rows=4):
    """Generate an RGB diagnostic pattern with numbered grid regions."""
    img = Image.new("RGB", (width, height), color="black")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 80)
    except OSError:
        font = ImageFont.load_default()

    cell_width = width // grid_cols
    cell_height = height // grid_rows
    colors = [
        (255, 255, 255),
        (128, 128, 128),
        (64, 64, 64),
        (192, 192, 192),
        (32, 32, 32),
        (96, 96, 96),
    ]

    region_num = 1
    for row in range(grid_rows):
        for col in range(grid_cols):
            x1 = col * cell_width
            y1 = row * cell_height
            x2 = x1 + cell_width
            y2 = y1 + cell_height
            color = colors[(row + col) % len(colors)]

            draw.rectangle([x1, y1, x2, y2], fill=color, outline="white", width=3)

            text = str(region_num)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = x1 + (cell_width - text_width) // 2
            text_y = y1 + (cell_height - text_height) // 2

            for offset_x in (-2, 0, 2):
                for offset_y in (-2, 0, 2):
                    draw.text(
                        (text_x + offset_x, text_y + offset_y),
                        text,
                        fill="black",
                        font=font,
                    )
            draw.text((text_x, text_y), text, fill="white", font=font)
            region_num += 1

    return np.array(img)
