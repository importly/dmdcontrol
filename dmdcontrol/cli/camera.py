from __future__ import annotations

import json
from importlib import import_module


def _discovery_module():
    return import_module("dmdcontrol.camera.discovery")


def _sync_check_module():
    return import_module("dmdcontrol.camera.sync_check")


def _sync_sweep_module():
    return import_module("dmdcontrol.camera.sync_sweep")


def _pair_capture_module():
    return import_module("dmdcontrol.camera.pair_capture")


def discover(argv):
    cameras = _discovery_module().discover_cameras()
    print(json.dumps(cameras, indent=2, sort_keys=True))
    return 0


def status(argv):
    status_payload = _discovery_module().camera_status()
    print(json.dumps(status_payload, indent=2, sort_keys=True))
    return 0


def sync_check(argv):
    return _sync_check_module().main(argv)


def sync_sweep(argv):
    return _sync_sweep_module().main(argv)


def pair_capture(argv):
    return _pair_capture_module().main(argv)
