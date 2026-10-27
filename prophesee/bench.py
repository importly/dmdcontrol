"""Quick test bench for the Prophesee camera on the rig. Run from the repo root:
    uv run prophesee/bench.py info                          camera identity + current biases
    uv run prophesee/bench.py rate -s 5                     event rate once per second for 5 s
    uv run prophesee/bench.py snap -o snap.png --ms 50      save one 50 ms accumulated event frame
    uv run prophesee/bench.py record -s 5 -o rec.raw        record 5 s of raw events
    uv run prophesee/bench.py rate --input rec.raw          replay a .raw file instead of the camera
    uv run prophesee/bench.py rate --bias bias_diff_on=20   set biases first (live only, repeatable)
    uv run prophesee/bench.py stream --fps 30               live video in the browser (see below)

stream serves MJPEG on localhost only. From your PC, open a tunnel and browse to

http://localhost:8080:

ssh -L 8080:localhost:8080 eodla

"""
import argparse
import io
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import evcam  # must come before any metavision import
import numpy as np
from metavision_core.event_io import EventsIterator
from PIL import Image, ImageDraw, ImageFont


def open_device(args):
    device = evcam.open_camera(args.input)
    biases = device.get_i_ll_biases()
    for spec in args.bias:
        name, value = spec.split("=")
        if biases is None or not biases.set(name, int(value)):
            raise SystemExit(f"could not set bias {spec}")
        print(f"bias {name} -> {biases.get(name)}")
    return device


def cmd_info(device, args):
    hw = device.get_i_hw_identification()
    geo = device.get_i_geometry()
    print(f"sensor:   {hw.get_sensor_info().name}")
    print(f"serial:   {hw.get_serial()}")
    print(f"geometry: {geo.get_width()} x {geo.get_height()}")
    print(f"format:   {hw.get_current_data_encoding_format()}")
    biases = device.get_i_ll_biases()
    if biases is not None:
        print("biases:")
        for name, value in sorted(biases.get_all_biases().items()):
            print(f"  {name:16s} {value}")


def cmd_rate(device, args):
    # 100 ms slices, summed and printed every 10 slices (1 s)
    it = EventsIterator.from_device(device, delta_t=100_000, max_duration=int(args.seconds * 1e6))
    on = off = 0
    for i, evs in enumerate(it, 1):
        n_on = int(np.count_nonzero(evs["p"]))
        on += n_on
        off += evs.size - n_on
        if i % 10 == 0:
            total = (on + off) / 1e6
            print(f"t={i / 10:5.1f}s  {total:6.2f} Mev/s  (ON {on / 1e6:.2f}  OFF {off / 1e6:.2f})")
            on = off = 0


def render(evs, height, width):
    img = np.full((height, width), 128, np.uint8)  # gray = no event, white = ON, black = OFF
    on = evs["p"] == 1
    img[evs["y"][on], evs["x"][on]] = 255
    img[evs["y"][~on], evs["x"][~on]] = 0
    return Image.fromarray(img)


def cmd_snap(device, args):
    it = EventsIterator.from_device(device, delta_t=int(args.ms * 1000))
    height, width = it.get_size()
    warmup = max(1, int(500 / args.ms))  # skip the first ~0.5 s while the sensor settles
    for i, evs in enumerate(it):
        if i < warmup:
            continue
        render(evs, height, width).save(args.output)
        print(f"wrote {args.output}: {evs.size} events over {args.ms:g} ms")
        break


def cmd_record(device, args):
    stream = device.get_i_events_stream()
    stream.log_raw_data(args.output)
    n = 0
    max_duration = int(args.seconds * 1e6)
    for evs in EventsIterator.from_device(device, delta_t=100_000, max_duration=max_duration):
        n += evs.size
    stream.stop_log_raw_data()
    print(f"wrote {args.output}: {n} events over {args.seconds:g} s")


def cmd_stream(device, args):
    latest = {"jpg": None, "n": 0}
    new_frame = threading.Condition()
    font = ImageFont.load_default(size=24)

    def produce():
        it = EventsIterator.from_device(device, delta_t=int(1e6 / args.fps))
        height, width = it.get_size()
        start = time.time()
        for i, evs in enumerate(it):
            if args.input:  # files decode faster than real time, so pace replay to the wall clock
                time.sleep(max(0.0, start + i / args.fps - time.time()))
            frame = render(evs, height, width)
            label = f"{evs.size * args.fps / 1e6:.2f} Mev/s"
            ImageDraw.Draw(frame).text((10, 8), label, fill=255, font=font)
            buf = io.BytesIO()
            frame.save(buf, format="JPEG", quality=80)
            with new_frame:
                latest["jpg"], latest["n"] = buf.getvalue(), latest["n"] + 1
                new_frame.notify_all()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/stream":
                page = (b'<html><body style="margin:0;background:#000">'
                        b'<img src="/stream" style="width:100%"></body></html>')
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(page)
                return
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            seen = 0
            try:
                while True:
                    with new_frame:
                        new_frame.wait_for(lambda: latest["n"] != seen)
                        jpg, seen = latest["jpg"], latest["n"]
                    header = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n"
                    self.wfile.write(header % len(jpg) + jpg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # browser tab closed

        def log_message(self, *_):
            pass

    threading.Thread(target=produce, daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"streaming at http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--input", default="", help="path to a .raw file (default: live camera)")
    common.add_argument("--bias", action="append", default=[], metavar="NAME=VALUE",
                        help="set a bias first")

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", parents=[common], help="print camera identity and biases")
    p = sub.add_parser("rate", parents=[common], help="print event rate once per second")
    p.add_argument("-s", "--seconds", type=float, default=5)
    p = sub.add_parser("snap", parents=[common], help="save one accumulated event frame as an image")
    p.add_argument("-o", "--output", default="snap.png")
    p.add_argument("--ms", type=float, default=33, help="accumulation window in ms")
    p = sub.add_parser("record", parents=[common], help="record raw events to a file")
    p.add_argument("-s", "--seconds", type=float, default=5)
    p.add_argument("-o", "--output", default="recording.raw")
    p = sub.add_parser("stream", parents=[common], help="serve live event frames as MJPEG over HTTP")
    p.add_argument("--fps", type=float, default=30,
                   help="frames per second (each frame = 1/fps of events)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--host", default="127.0.0.1",
                   help="0.0.0.0 to serve on the network (needs the port open)")
    args = parser.parse_args()

    device = open_device(args)
    commands = {"info": cmd_info, "rate": cmd_rate, "snap": cmd_snap, "record": cmd_record,
                "stream": cmd_stream}
    commands[args.cmd](device, args)


if __name__ == "__main__":
    main()
