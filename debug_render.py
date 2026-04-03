
import numpy as np
from PIL import Image

# Logic extracted from PatternEngine to avoid GLFW dependency
def pack_patterns(width, height, binary_images):
    r = np.zeros((height, width), dtype=np.uint8)
    g = np.zeros((height, width), dtype=np.uint8)
    b = np.zeros((height, width), dtype=np.uint8)
    for i in range(8):
        g |= (binary_images[i] << i)
        r |= (binary_images[i+8] << i)
        b |= (binary_images[i+16] << i)
    return np.stack([r, g, b], axis=-1)

def generate_checkerboard(width, height, block_size=32):
    y, x = np.indices((height, width))
    checker = ((x // block_size) + (y // block_size)) % 2
    checker = checker.astype(np.uint8)
    return [checker for _ in range(24)]

def save_diagnostic_images():
    width, height = 1920, 1080
    
    print(f"Generating {width}x{height} checkerboard (32x32 blocks)...")
    patterns = generate_checkerboard(width, height, block_size=32)
    packed_frame = pack_patterns(width, height, patterns)
    
    img_full = Image.fromarray(packed_frame)
    img_full.save("diagnostic_full_frame.png")
    print("Saved diagnostic_full_frame.png")
    
    # Visualize the 512x512 crop that main.py uses:
    # dlpc.set_input_display_resolution(704, 284, 512, 512)
    in_x, in_y, in_w, in_h = 704, 284, 512, 512
    crop_region = packed_frame[in_y:in_y+in_h, in_x:in_x+in_w]
    
    img_crop = Image.fromarray(crop_region)
    img_crop.save("diagnostic_crop_region.png")
    print(f"Saved diagnostic_crop_region.png (representing the {in_w}x{in_h} hardware crop)")

if __name__ == "__main__":
    save_diagnostic_images()
