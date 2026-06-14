from __future__ import annotations

import json


def _discovery_module():
    from dmdcontrol.camera import discovery

    return discovery


def _sync_check_module():
    from dmdcontrol.camera import sync_check

    return sync_check


def _sync_sweep_module():
    from dmdcontrol.camera import sync_sweep

    return sync_sweep


def _pair_capture_module():
    from dmdcontrol.camera import pair_capture

    return pair_capture


def _reprocess_aedat4_module():
    from dmdcontrol.camera import reprocess_aedat4

    return reprocess_aedat4


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


def reprocess_aedat4(argv):
    return _reprocess_aedat4_module().main(argv)
