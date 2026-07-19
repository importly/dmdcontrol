from __future__ import annotations

import json

from dmdcontrol.camera.discovery import camera_status, discover_cameras


def discover(argv):
    cameras = discover_cameras()
    print(json.dumps(cameras, indent=2, sort_keys=True))
    return 0


def status(argv):
    status_payload = camera_status()
    print(json.dumps(status_payload, indent=2, sort_keys=True))
    return 0
