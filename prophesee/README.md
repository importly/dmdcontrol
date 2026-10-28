# Prophesee camera library

Gen4.1 event camera (1280 x 720) used through OpenEB, Prophesee's open-source SDK, built on the rig in
`~/openeb/build-py314`. `evcam` is a Linux-only dependency

```bash
bash prophesee/setup_openeb.sh   # once per machine, ~5 min
uv sync
uv run prophesee/bench.py info   # all commands: uv run prophesee/bench.py --help
```

Other uv projects on the rig (Python 3.14): `uv add --editable ~/dmdcontrol/prophesee/evcam-lib`.

```python
import evcam
from metavision_core.event_io import EventsIterator

for evs in EventsIterator.from_device(evcam.open_camera(), delta_t=10_000):
    ...  # evs fields: x, y, p, t (us)
```

- Power up DC first, then USB. Don't press RST!!
- Only one process can use the camera at a time. A notebook holds it until its kernel restarts.
