import io
import json
import sys
import threading
import unittest
from urllib import error, request

import numpy as np
from PIL import Image


class DmdPreviewServerTests(unittest.TestCase):

    def setUp(self):
        from dmdcontrol.preview.server import create_server

        self.server = create_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)

    def _get(self, path):
        return request.urlopen(self.base_url + path, timeout=5)

    def test_import_and_server_start_do_not_load_hardware_modules(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        import dmdcontrol.preview.server  # noqa: F401

        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_root_returns_preview_html(self):
        with self._get("/") as response:
            html = response.read().decode("utf-8")

        self.assertEqual(response.status, 200)
        self.assertIn("DMD Bitplane Preview", html)
        self.assertIn("offline", html)

    def test_root_uses_preview_card_and_bottom_controls_ui(self):
        with self._get("/") as response:
            html = response.read().decode("utf-8")

        self.assertIn('id="sourceSwitch"', html)
        self.assertIn('class="preview-card"', html)
        self.assertIn('class="state-cache"', html)
        self.assertIn('class="state-token"', html)
        self.assertIn('id="liveStatus"', html)
        self.assertIn('class="control-panel"', html)
        self.assertIn('class="command-deck"', html)
        self.assertIn('class="control-surface"', html)
        self.assertIn('class="control-section source-section"', html)
        self.assertIn('class="control-section refresh-section"', html)
        self.assertIn('id="offlineControls"', html)
        self.assertIn('id="liveControls"', html)
        self.assertIn('id="lutSummary"', html)
        self.assertIn('id="lutEntries"', html)
        self.assertIn('id="planeButtons"', html)
        self.assertIn('class="plane-grid"', html)
        self.assertIn("els.offlineControls.hidden = live", html)
        self.assertIn("els.liveControls.hidden = !live", html)
        self.assertIn('params.set("view", "packed")', html)
        self.assertNotIn("<h1", html)
        self.assertNotIn("<h2", html)
        self.assertNotIn("DisplayPort output", html)
        self.assertNotIn("Packed Frame Preview", html)
        self.assertNotIn('class="preview-status-strip"', html)
        self.assertNotIn('class="bottom-panel"', html)
        self.assertNotIn('class="control-card"', html)
        self.assertNotIn('class="preview-titlebar"', html)
        self.assertNotIn('class="preview-badge-row"', html)
        self.assertNotIn('class="inspector-panel"', html)
        self.assertNotIn("<aside>", html)

    def test_config_lists_modes_and_bitplanes(self):
        with self._get("/api/config") as response:
            data = json.loads(response.read().decode("utf-8"))

        self.assertEqual(response.status, 200)
        self.assertIn("grid", data["pair_tests"])
        self.assertIn("grid", data["single_tests"])
        self.assertNotIn("coarse-grid", data["pair_tests"])
        self.assertNotIn("coarse-grid", data["single_tests"])
        self.assertEqual(data["bitplanes"][0], "G0")
        self.assertEqual(data["bitplanes"][8], "R0")
        self.assertFalse(data["live_frame_available"])
        self.assertEqual(data["live_metadata"], {})

    def test_offline_frame_endpoints_return_png(self):
        for path in (
                "/api/frame.png?layout=pair&test=grid&view=packed",
                "/api/frame.png?layout=pair&test=grid&view=bitplane&plane=0",
                "/api/frame.png?layout=pair&test=a-count-b-static&view=packed",
        ):
            with self.subTest(path=path):
                with self._get(path) as response:
                    body = response.read(8)

                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Content-Type"], "image/png")
                self.assertEqual(body, b"\x89PNG\r\n\x1a\n")

    def test_offline_frame_accepts_plane_labels_from_page_controls(self):
        for path in (
                "/api/frame.png?layout=pair&test=grid&view=packed&plane=G0&frame=0",
                "/api/frame.png?layout=pair&test=grid&view=bitplane&plane=G0&frame=0",
        ):
            with self.subTest(path=path):
                with self._get(path) as response:
                    body = response.read(8)

                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Content-Type"], "image/png")
                self.assertEqual(body, b"\x89PNG\r\n\x1a\n")

    def test_live_frame_returns_404_before_post_then_serves_posted_png(self):
        with self.assertRaises(error.HTTPError) as ctx:
            self._get("/api/live-frame.png")
        self.assertEqual(ctx.exception.code, 404)

        frame = np.zeros((4, 5, 3), dtype=np.uint8)
        frame[:, :, 1] = 1
        buf = io.BytesIO()
        Image.fromarray(frame).save(buf, format="PNG")
        metadata = {
            "layout": "pair",
            "test": "snake",
            "lut": {
                "entries": [
                    {
                        "index": 0,
                        "plane_index": 0,
                        "plane_label": "G0",
                        "start_us": 0,
                        "end_us": 600,
                        "segment_end_us": 600,
                    }],
                "timing": {
                    "effective_frame_hz": 60.0,
                    "entries_count": 1},
            },
        }
        req = request.Request(
            self.base_url + "/api/live-frame",
            data=buf.getvalue(),
            method="POST",
            headers={
                "Content-Type": "image/png",
                "X-DMD-Metadata": json.dumps(metadata),
            },
        )
        with request.urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 204)

        with self._get("/api/config") as response:
            config = json.loads(response.read().decode("utf-8"))

        self.assertTrue(config["live_frame_available"])
        self.assertEqual(config["live_metadata"]["test"], "snake")
        self.assertEqual(config["live_metadata"]["lut"]["entries"][0]["plane_label"], "G0")

        with self._get("/api/live-frame.png?view=bitplane&plane=0") as response:
            png = response.read()

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

        with self._get("/api/live-frame.png?view=bitplane&plane=G0") as response:
            labeled_plane_png = response.read()

        self.assertTrue(labeled_plane_png.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
