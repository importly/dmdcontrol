# On your PC: ssh -L 8080:localhost:8080 eodla, then open http://localhost:8080
import io
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import evcam
import numpy as np
from PIL import Image
from metavision_sdk_stream import Camera, CameraStreamSlicer, SliceCondition

with evcam.quiet_stderr():
    camera = Camera.from_first_available()
slicer = CameraStreamSlicer(camera.move(), slice_condition=SliceCondition.make_n_us(10_000))
height, width = slicer.camera().height(), slicer.camera().width()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        batch, last = [], time.time()
        try:
            for s in slicer:
                batch.append(s.events.copy())
                if time.time() - last > 1 / 30:
                    events = np.concatenate(batch)
                    on = events["p"] == 1
                    img = np.full((height, width), 128, np.uint8)
                    img[events["y"][on], events["x"][on]] = 255
                    img[events["y"][~on], events["x"][~on]] = 0
                    buf = io.BytesIO()
                    Image.fromarray(img).save(buf, format="JPEG")
                    jpg = buf.getvalue()
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                    batch, last = [], time.time()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *_):
        pass


try:
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()
except KeyboardInterrupt:
    pass
