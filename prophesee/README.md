# Prophesee camera library

Gen4.1 event camera (1280 x 720) used through OpenEB, Prophesee's open-source SDK, built on the rig in
`~/openeb/build-py314`. `evcam` is a Linux-only dependency

```bash
bash prophesee/setup_openeb.sh   # once per machine, ~5 min
uv sync
```

Other uv projects on the rig (Python 3.14): `uv add --editable ~/dmdcontrol/prophesee/evcam-lib`.

```python
import evcam
from metavision_sdk_stream import Camera, CameraStreamSlicer, SliceCondition

with evcam.quiet_stderr():
    camera = Camera.from_first_available()
for s in CameraStreamSlicer(camera.move(), slice_condition=SliceCondition.make_n_us(10_000)):
    ...  # s.events fields: x, y, p, t (us)
```

- Power up DC first, then USB. Don't press RST!!
- Only one process can use the camera at a time. A notebook holds it until its kernel restarts.
