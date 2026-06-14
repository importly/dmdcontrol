import time

import glfw
import numpy as np
from OpenGL.GL import *

from dmdcontrol.patterns.bitplanes import pack_bitplanes_rgb, unpack_rgb_bitplanes
from dmdcontrol.support.constants import DMD_HEIGHT, DMD_WIDTH, TARGET_HZ
from dmdcontrol.support.logging import logger


class PatternEngine:

    def __init__(self, width=DMD_WIDTH, height=DMD_HEIGHT, monitor_index=0, fps=TARGET_HZ):
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
                "GLFW found no monitors after 5 seconds. Is the display connected and X11 running?")

        if len(monitors) > monitor_index:
            monitor = monitors[monitor_index]
        else:
            monitor = monitors[0]
            logger.warning(f"[WARNING] Monitor {monitor_index} not found, using primary.")

        glfw.window_hint(glfw.DECORATED, glfw.FALSE)
        glfw.window_hint(glfw.RESIZABLE, glfw.FALSE)
        glfw.window_hint(glfw.AUTO_ICONIFY, glfw.FALSE)
        glfw.window_hint(glfw.REFRESH_RATE, self.fps)

        self.window = glfw.create_window(width, height, "DLPC900 Pattern Engine", monitor, None)

        if not self.window:
            glfw.terminate()
            raise RuntimeError("Could not create GLFW window")

        glfw.make_context_current(self.window)
        glfw.swap_interval(1)  # Sync to VSync

        mode = glfw.get_video_mode(monitor)
        if mode is not None:
            logger.info(
                f"[+] GLFW video mode: {mode.size.width}x{mode.size.height} @ {mode.refresh_rate}Hz "
                f"(requested {width}x{height} @ {self.fps}Hz)")

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
        WARNING: This requires RGB 4:4:4 video without YCbCr chroma subsampling. make sure nvidia or opensource drivers support it
        """
        return pack_bitplanes_rgb(binary_images, self.width, self.height)

    def rgb_to_binary_patterns(self, rgb_array):
        """
        Convert RGB888 image to 24 binary bit-plane patterns.

        Args:
            rgb_array: numpy array with shape (height, width, 3) containing RGB values 0-255

        Returns:
            List of 24 binary numpy arrays (values 0 or 1)
            Order: G0-G7, R0-R7, B0-B7 (matches DLPC900 bit-plane extraction)
        """
        return unpack_rgb_bitplanes(rgb_array, self.width, self.height)

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

    def generate_snake_frame(self, grid_w=24, grid_h=13):
        import random
        # Initialize snake state if it doesn't exist
        if not hasattr(self, 'snake_pos'):
            self.snake_pos = [
                (grid_w // 2,
                 grid_h // 2),
                (grid_w // 2 - 1,
                 grid_h // 2),
                (grid_w // 2 - 2,
                 grid_h // 2),
                (grid_w // 2 - 3,
                 grid_h // 2)]
            self.snake_dir = (1, 0)

        # Move snake
        head_x, head_y = self.snake_pos[0]
        dx, dy = self.snake_dir

        # Randomly change direction, but don't reverse
        if random.random() < 0.2:
            possible_dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
            possible_dirs = [(nx, ny) for nx, ny in possible_dirs if (nx, ny) != (-dx, -dy)]
            self.snake_dir = random.choice(possible_dirs)
            dx, dy = self.snake_dir

        new_head = (head_x + dx, head_y + dy)
        new_head = (new_head[0] % grid_w, new_head[1] % grid_h)

        self.snake_pos.insert(0, new_head)
        self.snake_pos.pop()  # remove tail

        # Draw grid
        grid = np.zeros((grid_h, grid_w), dtype=np.uint8)
        for x, y in self.snake_pos:
            grid[y, x] = 255

        # Fast nearest neighbor scaling
        block_w = self.width // grid_w
        block_h = self.height // grid_h
        frame_2d = np.repeat(np.repeat(grid, block_h, axis=0), block_w, axis=1)

        # Pad if there are remainder pixels
        if frame_2d.shape != (self.height, self.width):
            padded = np.zeros((self.height, self.width), dtype=np.uint8)
            h, w = frame_2d.shape
            padded[:min(h, self.height), :min(w, self.width)] = frame_2d[:min(h, self.height), :min(
                w, self.width)]
            frame_2d = padded

        # Return directly packed RGB frame (pure Grayscale for chroma bypass)
        return np.ascontiguousarray(np.stack([frame_2d, frame_2d, frame_2d], axis=-1))

    def generate_clock_frame(self):
        """
        Generates a 1920x1080 pure grayscale frame with a massive microsecond clock timestamp.
        """
        from datetime import datetime

        # We need cv2 to render the text
        import cv2

        canvas = np.zeros((self.height, self.width), dtype=np.uint8)

        # Format: HH:MM:SS.usec
        time_str = datetime.now().strftime("%H:%M:%S.%f")

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 9
        thickness = 15
        color = 255

        # Roughly center the text
        text_size = cv2.getTextSize(time_str, font, font_scale, thickness)[0]
        text_x = (self.width - text_size[0]) // 2
        text_y = (self.height + text_size[1]) // 2

        cv2.putText(
            canvas,
            time_str,
            (text_x,
             text_y),
            font,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA)

        # flip the image Y axis
        # canvas = np.flip(canvas, axis=0)

        # flip the image X axis
        canvas = np.flip(canvas, axis=1)

        return np.ascontiguousarray(np.stack([canvas, canvas, canvas], axis=-1))

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

            img[y_start:y_start + sub_height, bx_start:bx_end] = 1
            patterns.append(img)
        return patterns

    def should_close(self):
        return (
            glfw.window_should_close(self.window) or glfw.get_key(self.window,
                                                                  glfw.KEY_ESCAPE) == glfw.PRESS)

    def cleanup(self):
        glfw.terminate()
