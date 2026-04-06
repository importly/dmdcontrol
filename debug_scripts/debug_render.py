import os

import numpy as np
from PIL import Image


def pack_patterns(width, height, binary_images):
    r = np.zeros((height, width), dtype=np.uint8)
    g = np.zeros((height, width), dtype=np.uint8)
    b = np.zeros((height, width), dtype=np.uint8)
    for i in range(8):
        g |= binary_images[i] << i
        r |= binary_images[i + 8] << i
        b |= binary_images[i + 16] << i
    return np.stack([r, g, b], axis=-1)


def generate_checkerboard(width, height, block_size=32):
    y, x = np.indices((height, width))
    checker = ((x // block_size) + (y // block_size)) % 2
    checker = checker.astype(np.uint8)
    return [checker for _ in range(24)]


def generate_lines(width, height):
    y, x = np.indices((height, width))
    lines = (x % 2).astype(np.uint8)
    return [lines for _ in range(24)]


def generate_solid(width, height, val):
    solid = np.full((height, width), val, dtype=np.uint8)
    return [solid for _ in range(24)]


def generate_gradient(width, height):
    patterns = []
    x = np.indices((height, width))[1]
    for i in range(24):
        threshold = (width / 24) * i
        grad = (x >= threshold).astype(np.uint8)
        patterns.append(grad)
    return patterns


def save_diagnostic_images():
    width, height = 1920, 1080
    out_dir = "diagnostic_images"
    os.makedirs(out_dir, exist_ok=True)

    print(f"Generating {width}x{height} diagnostic images...")

    tests = {
        "checkerboard": generate_checkerboard(width, height, block_size=32),
        "single_pixel": generate_checkerboard(width, height, block_size=1),
        "lines": generate_lines(width, height),
        "solid_white": generate_solid(width, height, 1),
        "gradient": generate_gradient(width, height),
    }

    for name, patterns in tests.items():
        packed_frame = pack_patterns(width, height, patterns)

        # When saving 24 packed bits to an RGB PNG, the colors will look weird to a human,
        # but that's exactly what the DLPC900 needs to extract 24 bit-planes.
        img = Image.fromarray(packed_frame)
        filename = os.path.join(out_dir, f"diagnostic_{name}.png")
        img.save(filename)
        print(f"Saved {filename}")


if __name__ == "__main__":
    save_diagnostic_images()
