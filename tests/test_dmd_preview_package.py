import importlib
import sys
import unittest


class DmdPreviewPackageTests(unittest.TestCase):
    def test_package_server_exports_root_api_without_hardware_imports(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        root = importlib.import_module("dmd_preview_server")
        server = importlib.import_module("dmdcontrol.preview.server")
        html = importlib.import_module("dmdcontrol.preview.html")

        self.assertIs(root.DmdPreviewHandler, server.DmdPreviewHandler)
        self.assertIs(root.DmdPreviewServer, server.DmdPreviewServer)
        self.assertIs(root.create_server, server.create_server)
        self.assertIs(root.main, server.main)
        self.assertIs(root.INDEX_HTML, html.INDEX_HTML)
        self.assertIs(root.BITPLANE_LABELS, server.BITPLANE_LABELS)
        self.assertIs(root.LiveFrameStore, server.LiveFrameStore)
        self.assertIs(root.render_png_bytes, server.render_png_bytes)
        self.assertIs(root.render_preview_png, server.render_preview_png)
        self.assertIs(root.render_view_image, server.render_view_image)
        self.assertIs(root.PAIR_TESTS, server.PAIR_TESTS)
        self.assertIs(root.STATIC_PAIR_TESTS, server.STATIC_PAIR_TESTS)
        self.assertIs(root.PATTERN_NAMES, server.PATTERN_NAMES)
        self.assertEqual(server.INDEX_HTML, html.INDEX_HTML)
        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))

    def test_preview_package_import_is_lightweight(self):
        for module_name in (
                "dmdcontrol.preview",
                "dmdcontrol.preview.server",
                "dmdcontrol.preview.render",
        ):
            sys.modules.pop(module_name, None)

        importlib.import_module("dmdcontrol.preview")

        self.assertNotIn("dmdcontrol.preview.server", sys.modules)
        self.assertNotIn("dmdcontrol.preview.render", sys.modules)


if __name__ == "__main__":
    unittest.main()
