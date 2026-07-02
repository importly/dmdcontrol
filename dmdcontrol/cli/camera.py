from __future__ import annotations

import json


def _discovery_module():
    from dmdcontrol.camera import discovery

    return discovery


def discover(argv):
    cameras = _discovery_module().discover_cameras()
    print(json.dumps(cameras, indent=2, sort_keys=True))
    return 0


def status(argv):
    status_payload = _discovery_module().camera_status()
    print(json.dumps(status_payload, indent=2, sort_keys=True))
    return 0


def sync_check(argv):
    from dmdcontrol.camera import sync_check as sync_check_module

    return sync_check_module.main(argv)


def pair_capture(argv):
    from dmdcontrol.camera import pair_capture as pair_capture_module

    return pair_capture_module.main(argv)


def reprocess_aedat4(argv):
    from dmdcontrol.camera import reprocess_aedat4 as reprocess_aedat4_module

    return reprocess_aedat4_module.main(argv)
