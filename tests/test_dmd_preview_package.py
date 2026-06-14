import importlib
import sys
import unittest


class DmdPreviewPackageTests(unittest.TestCase):

    def test_package_server_exports_preview_api_without_hardware_imports(self):
        for module_name in ("glfw", "OpenGL.GL", "dlpc900_hid"):
            sys.modules.pop(module_name, None)

        server = importlib.import_module("dmdcontrol.preview.server")
        html = importlib.import_module("dmdcontrol.preview.html")

        self.assertEqual(server.INDEX_HTML, html.INDEX_HTML)
        self.assertTrue(callable(server.create_server))
        self.assertTrue(callable(server.main))
        self.assertTrue(hasattr(server, "DmdPreviewHandler"))
        self.assertTrue(hasattr(server, "DmdPreviewServer"))
        self.assertTrue(server.BITPLANE_LABELS)
        self.assertTrue(server.PAIR_TESTS)
        self.assertTrue(server.STATIC_PAIR_TESTS)
        self.assertTrue(server.PATTERN_NAMES)
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
