import numpy as np
from PIL import Image


def generate_solid_color(color_idx, width=1920, height=1080):
    """
    Generate solid colors: 0=Red, 1=Green, 2=Blue
    This helps test if the DisplayPort is crossing color channels.
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :, color_idx] = 255
    return img


def rgb_to_binary_patterns(rgb_array):
    patterns = []
    # Green channel: bits 0-7
    for bit in range(8):
        patterns.append((rgb_array[:, :, 1] >> bit) & 1)
    # Red channel: bits 8-15
    for bit in range(8):
        patterns.append((rgb_array[:, :, 0] >> bit) & 1)
    # Blue channel: bits 16-23
    for bit in range(8):
        patterns.append((rgb_array[:, :, 2] >> bit) & 1)
    return patterns


def pack_patterns(binary_images, width=1920, height=1080):
    r = np.zeros((height, width), dtype=np.uint8)
    g = np.zeros((height, width), dtype=np.uint8)
    b = np.zeros((height, width), dtype=np.uint8)
    for i in range(8):
        g |= binary_images[i] << i
        r |= binary_images[i + 8] << i
        b |= binary_images[i + 16] << i
    return np.stack([r, g, b], axis=-1)


# Generate tests
for name, idx in [("pure_red", 0), ("pure_green", 1), ("pure_blue", 2)]:
    rgb = generate_solid_color(idx)
    patterns = rgb_to_binary_patterns(rgb)
    frame = pack_patterns(patterns)
    Image.fromarray(frame).save(f"diagnostic_{name}_packed.png")
    print(f"Generated diagnostic_{name}_packed.png")
