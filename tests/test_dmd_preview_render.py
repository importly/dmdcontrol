import io
import sys
import unittest

import numpy as np
from PIL import Image


class DmdPreviewRenderTests(unittest.TestCase):
    def test_import_does_not_load_hardware_modules(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        import dmdcontrol.preview.render  # noqa: F401

        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_bitplane_labels_and_mapping_match_dlpc900_packing(self):
        from dmdcontrol.preview.render import BITPLANE_LABELS, extract_bitplane

        packed = np.zeros((2, 3, 3), dtype=np.uint8)
        packed[0, 0, 1] = 0b00000001
        packed[0, 1, 0] = 0b00000001
        packed[0, 2, 2] = 0b00000001

        self.assertEqual(BITPLANE_LABELS[0], "G0")
        self.assertEqual(BITPLANE_LABELS[8], "R0")
        self.assertEqual(BITPLANE_LABELS[16], "B0")
        self.assertEqual(extract_bitplane(packed, 0)[0, 0], 255)
        self.assertEqual(extract_bitplane(packed, 8)[0, 1], 255)
        self.assertEqual(extract_bitplane(packed, 16)[0, 2], 255)
        self.assertEqual(extract_bitplane(packed, 0)[0, 1], 0)

    def test_offline_paired_coarse_grid_places_b_left_and_a_right(self):
        from dmdcontrol.patterns.paired import DMD_HEIGHT, DMD_WIDTH, generate_static_frame
        from dmdcontrol.preview.render import render_offline_frame

        frame = render_offline_frame(layout="pair", test="coarse-grid")

        self.assertEqual(frame.shape, (DMD_HEIGHT, DMD_WIDTH * 2, 3))
        np.testing.assert_array_equal(
            frame[:, :DMD_WIDTH, :],
            generate_static_frame("coarse-grid", route_label="B"),
        )
        np.testing.assert_array_equal(
            frame[:, DMD_WIDTH:, :],
            generate_static_frame("coarse-grid", route_label="A"),
        )

    def test_bitplane_render_is_binary_grayscale(self):
        from dmdcontrol.preview.render import render_bitplane_image, render_offline_frame

        frame = render_offline_frame(layout="pair", test="coarse-grid")
        bitplane = render_bitplane_image(frame, plane=0)

        self.assertEqual(bitplane.shape, frame.shape[:2])
        self.assertEqual(bitplane.dtype, np.uint8)
        self.assertTrue(np.isin(bitplane, [0, 255]).all())

    def test_lut_preview_metadata_labels_entries_and_timing_windows(self):
        from dmdcontrol.preview.render import build_lut_preview_metadata

        entries = [
            (0, 600, False, 1, 7, 10, False, 0),
            (8, 600, False, 1, 7, 10, False, 8),
            (16, 600, True, 1, 7, 10, True, 16),
        ]
        timing = {
            "entries_count": 3,
            "effective_frame_hz": 60.0,
            "exposure_us": 600,
            "dark_us": 10,
            "total_sequence_us": 1830,
        }

        metadata = build_lut_preview_metadata(entries, timing)

        self.assertEqual(metadata["entries"][0]["plane_label"], "G0")
        self.assertEqual(metadata["entries"][1]["plane_label"], "R0")
        self.assertEqual(metadata["entries"][2]["plane_label"], "B0")
        self.assertEqual(metadata["entries"][1]["start_us"], 610)
        self.assertEqual(metadata["entries"][1]["end_us"], 1210)
        self.assertEqual(metadata["entries"][2]["segment_end_us"], 1830)
        self.assertTrue(metadata["entries"][2]["clear"])
        self.assertTrue(metadata["entries"][2]["trig2_disabled"])
        self.assertEqual(metadata["timing"]["effective_frame_hz"], 60.0)

    def test_png_render_outputs_png_bytes(self):
        from dmdcontrol.preview.render import render_png_bytes

        packed = np.zeros((4, 5, 3), dtype=np.uint8)
        png = render_png_bytes(packed)

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        decoded = Image.open(io.BytesIO(png))
        self.assertEqual(decoded.size, (5, 4))


if __name__ == "__main__":
    unittest.main()
