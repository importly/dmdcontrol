import glfw
from OpenGL.GL import *
import numpy as np
import time
from logger import logger


class PatternEngine:
    def __init__(self, width=1920, height=1080, monitor_index=0, fps=60):
        self.width = width
        self.height = height
        self.fps = fps

        # Stutter tracking
        self.last_frame_time = 0.0
        self.expected_frame_time = 1.0 / fps  # dynamic Hz target
        self.dropped_frames = 0
        self.last_stutter_log = 0.0

        if not glfw.init():
            raise RuntimeError("Could not initialize GLFW")

        monitors = glfw.get_monitors()
        attempts = 0
        while not monitors and attempts < 10:
            time.sleep(0.5)
            monitors = glfw.get_monitors()
            attempts += 1

        if not monitors:
            raise TimeoutError(
                "GLFW found no monitors after 5 seconds. Is the display connected and X11 running?"
            )

        if len(monitors) > monitor_index:
            monitor = monitors[monitor_index]
        else:
            monitor = monitors[0]
            logger.warning(
                f"[WARNING] Monitor {monitor_index} not found, using primary."
            )

        # Create a borderless window
        glfw.window_hint(glfw.DECORATED, glfw.FALSE)
        glfw.window_hint(glfw.RESIZABLE, glfw.FALSE)
        glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
        glfw.window_hint(glfw.REFRESH_RATE, self.fps)  # Request dynamic refresh rate

        self.window = glfw.create_window(
            width, height, "DLPC900 Pattern Engine", monitor, None
        )

        if not self.window:
            glfw.terminate()
            raise RuntimeError("Could not create GLFW window")

        glfw.make_context_current(self.window)
        glfw.swap_interval(1)  # Sync to VSync

        # Verify 1:1 Framebuffer scaling
        fb_w, fb_h = glfw.get_framebuffer_size(self.window)
        if fb_w != width or fb_h != height:
            logger.warning(
                f"[WARNING] Framebuffer size {fb_w}x{fb_h} does not match requested {width}x{height}! 1:1 pixel mapping will fail."
            )

        glViewport(0, 0, fb_w, fb_h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, width, height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        self.tex_id = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

    def pack_patterns(self, binary_images):
        """
        Packs 24 independent binary masks into a single 24-bit RGB frame.
        WARNING: This requires RGB 4:4:4 video without YCbCr chroma subsampling.
        """
        r = np.zeros((self.height, self.width), dtype=np.uint8)
        g = np.zeros((self.height, self.width), dtype=np.uint8)
        b = np.zeros((self.height, self.width), dtype=np.uint8)
        for i in range(8):
            g |= binary_images[i] << i
            r |= binary_images[i + 8] << i
            b |= binary_images[i + 16] << i
        return np.ascontiguousarray(np.stack([r, g, b], axis=-1))

    def pack_patterns_safe_8bit(self, binary_images):
        """
        Future-proof wrapper that packs up to 8 independent binary masks into a pure grayscale frame.
        Because R=G=B, this perfectly bypasses Linux YCbCr chroma subsampling and dithering natively.
        The 8 bitplanes are duplicated across Green, Red, and Blue channels for a total of 24 planes.
        
        Args:
            binary_images: List of up to 8 binary numpy arrays (0 or 1)
        """
        if len(binary_images) > 8:
            logger.warning("[WARNING] pack_patterns_safe_8bit received more than 8 patterns. Only the first 8 will be used.")
            
        gray = np.zeros((self.height, self.width), dtype=np.uint8)
        for i in range(min(8, len(binary_images))):
            gray |= binary_images[i] << i
            
        # Duplicate the gray channel into R, G, and B
        return np.ascontiguousarray(np.stack([gray, gray, gray], axis=-1))

    def rgb_to_binary_patterns(self, rgb_array):
        """
        Convert RGB888 image to 24 binary bit-plane patterns.

        Args:
            rgb_array: numpy array with shape (height, width, 3) containing RGB values 0-255

        Returns:
            List of 24 binary numpy arrays (values 0 or 1)
            Order: G0-G7, R0-R7, B0-B7 (matches DLPC900 bit-plane extraction)
        """
        if rgb_array.shape[:2] != (self.height, self.width):
            raise ValueError(
                f"RGB array must be {self.height}x{self.width}, got {rgb_array.shape[:2]}"
            )

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

    def display_frame(self, frame_array):
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGB8,
            self.width,
            self.height,
            0,
            GL_RGB,
            GL_UNSIGNED_BYTE,
            frame_array,
        )
        glClear(GL_COLOR_BUFFER_BIT)
        glEnable(GL_TEXTURE_2D)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(0, 0)
        glTexCoord2f(1, 0)
        glVertex2f(self.width, 0)
        glTexCoord2f(1, 1)
        glVertex2f(self.width, self.height)
        glTexCoord2f(0, 1)
        glVertex2f(0, self.height)
        glEnd()
        glDisable(GL_TEXTURE_2D)

        # Stutter Detection Logic
        # swap_buffers blocks until VSync
        glfw.swap_buffers(self.window)

        current_time = glfw.get_time()
        if self.last_frame_time > 0.0:
            delta = current_time - self.last_frame_time
            # If the frame took > 1.5x the expected duration, we missed a VSync deadline
            if delta > self.expected_frame_time * 1.5:
                self.dropped_frames += 1
                # Rate limit the stutter warning to once every 2 seconds
                if current_time - self.last_stutter_log > 2.0:
                    logger.warning(
                        f"[WARNING] Stutter Detected! Frame took {delta * 1000:.2f}ms. Total dropped: {self.dropped_frames}"
                    )
                    self.last_stutter_log = current_time

        self.last_frame_time = current_time

        glfw.poll_events()

    def check_trigger_key(self):
        """Check if the spacebar was just pressed."""
        if glfw.get_key(self.window, glfw.KEY_SPACE) == glfw.PRESS:
            # Simple debounce: wait until key is released
            while glfw.get_key(self.window, glfw.KEY_SPACE) == glfw.PRESS:
                glfw.poll_events()
                time.sleep(0.01)
            return True
        return False

    def generate_checkerboard(self, block_size=32):
        y, x = np.indices((self.height, self.width))
        checker = ((x // block_size) + (y // block_size)) % 2
        checker = checker.astype(np.uint8)
        return [checker for _ in range(24)]

    def generate_lines(self):
        y, x = np.indices((self.height, self.width))
        # 1-pixel wide vertical lines
        lines = (x % 2).astype(np.uint8)
        return [lines for _ in range(24)]

    def generate_solid(self, val):
        solid = np.full((self.height, self.width), val, dtype=np.uint8)
        return [solid for _ in range(24)]

    def generate_gradient(self):
        patterns = []
        x = np.indices((self.height, self.width))[1]
        
        # Build 24 bitplanes. To bypass YCbCr chroma subsampling on Linux, 
        # we must ensure the packed RGB buffer is purely grayscale (R=G=B).
        # We do this by grouping the 24 bitplanes into 8 spatial bands.
        # Bit 0 of G, R, B all turn on at band 0. Bit 1 at band 1, etc.
        for i in range(24):
            bit_index = i % 8  # Modulo 8 ensures patterns 0=8=16, 1=9=17, etc.
            threshold = (self.width / 8) * bit_index
            grad = (x >= threshold).astype(np.uint8)
            patterns.append(grad)
        return patterns

    def generate_ordering_diagnostic_patterns(self, sub_width=512, sub_height=512):
        patterns = []
        # Create a sweeping bar or sequential block for each bitplane 0 to 23
        for i in range(24):
            img = np.zeros((self.height, self.width), dtype=np.uint8)
            y_start = (self.height - sub_height) // 2
            x_start = (self.width - sub_width) // 2

            # Draw a block that moves to the right depending on the bit index
            # Each block is sub_height tall, sub_width//24 wide
            block_w = max(1, sub_width // 24)
            bx_start = x_start + (i * block_w)
            bx_end = min(x_start + sub_width, bx_start + block_w)

            img[y_start : y_start + sub_height, bx_start:bx_end] = 1
            patterns.append(img)
        return patterns

    def generate_subscale_patterns(self, sub_width=512, sub_height=512):
        patterns = []
        for i in range(24):
            img = np.zeros((self.height, self.width), dtype=np.uint8)
            y_start = (self.height - sub_height) // 2
            x_start = (self.width - sub_width) // 2
            img[y_start : y_start + sub_height, x_start : x_start + sub_width] = (
                np.random.rand(sub_height, sub_width) > 0.5
            ).astype(np.uint8)
            patterns.append(img)
        return patterns

    def should_close(self):
        return (
            glfw.window_should_close(self.window)
            or glfw.get_key(self.window, glfw.KEY_ESCAPE) == glfw.PRESS
        )

    def cleanup(self):
        glfw.terminate()
