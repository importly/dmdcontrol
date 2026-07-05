from __future__ import annotations

import gc
from dataclasses import is_dataclass, replace

from dmdcontrol.camera.capture import flush_stale_batches, validate_camera_ready
from dmdcontrol.camera.discovery import (
    configure_camera_performance,
    configure_rising_edge_triggers,
    open_camera_capture,
)


def _ready_with_initial_flush(ready, initial_flush):
    if is_dataclass(ready):
        return replace(ready, initial_flush=initial_flush)
    try:
        setattr(ready, "initial_flush", initial_flush)
    except Exception:
        pass
    return ready


def _open_configured_camera_capture(args):
    import dv_processing as dv

    capture = None
    try:
        capture = open_camera_capture(dv)
        configure_camera_performance(
            capture,
            bias_sensitivity=args.bias_sensitivity,
            efps=args.efps,
        )
        trigger_configuration = configure_rising_edge_triggers(capture)
        ready = validate_camera_ready(
            capture,
            stream_rearm=None,
            trigger_configuration=trigger_configuration,
        )
    except Exception:
        if capture is not None:
            del capture
        gc.collect()
        raise
    return capture, ready


def open_camera_writer(run, capture):
    import dv_processing as dv

    return dv.io.MonoCameraWriter(str(run.raw_recording_path), capture)


def open_ready_camera(run, args):
    capture = None
    writer = None
    try:
        capture, ready = _open_configured_camera_capture(args)
        writer = open_camera_writer(run, capture)
        initial_flush = flush_stale_batches(capture, reads=args.camera_flush_reads)
        ready = _ready_with_initial_flush(ready, initial_flush)
    except Exception:
        if writer is not None:
            del writer
        if capture is not None:
            del capture
        gc.collect()
        raise
    return capture, writer, ready


def close_camera_resources(resources):
    writer = resources.pop("writer", None)
    capture = resources.pop("capture", None)
    if writer is not None:
        del writer
    if capture is not None:
        del capture
    gc.collect()
