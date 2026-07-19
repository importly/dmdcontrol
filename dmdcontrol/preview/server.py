"""Local HTTP server for DMD packed-frame and bitplane previews."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from dmdcontrol.patterns.modes import PATTERN_NAMES
from dmdcontrol.patterns.paired import PAIR_TESTS, STATIC_PAIR_TESTS
from dmdcontrol.preview.html import INDEX_HTML
from dmdcontrol.preview.render import (
    BITPLANE_LABELS,
    LiveFrameStore,
    render_png_bytes,
    render_preview_png,
    render_view_image,
)


class DmdPreviewHandler(BaseHTTPRequestHandler):
    server_version = "DmdPreview/1.0"

    @property
    def preview_server(self) -> DmdPreviewServer:
        if not isinstance(self.server, DmdPreviewServer):
            raise TypeError("preview handler requires DmdPreviewServer")
        return self.server

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/":
                self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/config":
                self._send_json(self._config_payload())
            elif parsed.path == "/api/frame.png":
                self._send_offline_frame(params)
            elif parsed.path == "/api/live-frame.png":
                self._send_live_frame(params)
            else:
                self.send_error(404, "not found")
        except ValueError as exc:
            self.send_error(400, str(exc))

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/live-frame":
            self.send_error(404, "not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        metadata = {}
        raw_metadata = self.headers.get("X-DMD-Metadata")
        if raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except json.JSONDecodeError:
                metadata = {}
        try:
            self.preview_server.live_store.set_png(body, metadata=metadata)
        except Exception as exc:
            self.send_error(400, str(exc))
            return
        self.send_response(204)
        self.end_headers()

    def _config_payload(self):
        metadata, updated_at = self.preview_server.live_store.get_metadata()
        return {
            "default_layout": "pair",
            "single_tests": list(PATTERN_NAMES),
            "pair_tests": list(PAIR_TESTS),
            "static_pair_tests": list(STATIC_PAIR_TESTS),
            "bitplanes": list(BITPLANE_LABELS),
            "live_frame_available": self.preview_server.live_store.has_frame(),
            "live_metadata": metadata,
            "live_updated_at": updated_at,
        }

    def _send_offline_frame(self, params):
        layout = _query_value(params, "layout", "pair")
        test = _query_value(params, "test", "grid")
        test_a = _query_value(params, "test_a", None)
        test_b = _query_value(params, "test_b", None)
        frame_index = int(_query_value(params, "frame", 0))
        view = _query_value(params, "view", "packed")
        plane = _query_plane(params, "plane", 0)
        png = render_preview_png(
            layout=layout,
            test=test,
            test_a=test_a,
            test_b=test_b,
            frame_index=frame_index,
            view=view,
            plane=plane,
        )
        self._send_bytes(png, "image/png")

    def _send_live_frame(self, params):
        frame, _metadata, _updated_at = self.preview_server.live_store.get_frame()
        if frame is None:
            self.send_error(404, "no live frame")
            return
        view = _query_value(params, "view", "packed")
        plane = _query_plane(params, "plane", 0)
        png = render_png_bytes(render_view_image(frame, view=view, plane=plane))
        self._send_bytes(png, "image/png")

    def _send_json(self, payload):
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self._send_bytes(body, "application/json")

    def _send_bytes(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DmdPreviewServer(ThreadingHTTPServer):

    def __init__(self, server_address):
        super().__init__(server_address, DmdPreviewHandler)
        self.live_store = LiveFrameStore()


def _query_value(params, name, default):
    values = params.get(name)
    if not values:
        return default
    return values[0] or default


def _query_plane(params, name, default):
    value = _query_value(params, name, None)
    if value is None:
        return default
    if value in BITPLANE_LABELS:
        return BITPLANE_LABELS.index(value)
    plane = int(value)
    if plane < 0 or plane >= len(BITPLANE_LABELS):
        raise ValueError(f"plane must be in [0, {len(BITPLANE_LABELS) - 1}]")
    return plane


def create_server(host="127.0.0.1", port=8080):
    return DmdPreviewServer((host, int(port)))


def _build_parser():
    parser = argparse.ArgumentParser(description="Serve DMD bitplane preview UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    server = create_server(args.host, args.port)
    host, port = server.server_address[:2]
    print(f"Serving DMD preview at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
