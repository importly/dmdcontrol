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
        self.assertEqual(server.INDEX_HTML, html.INDEX_HTML)
        self.assertFalse({"glfw", "OpenGL.GL", "dlpc900_hid"} & set(sys.modules))


if __name__ == "__main__":
    unittest.main()
