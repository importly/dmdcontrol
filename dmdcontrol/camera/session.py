from __future__ import annotations

from dataclasses import is_dataclass, replace
import gc

from dmdcontrol.camera.capture import flush_stale_batches, validate_camera_ready
from dmdcontrol.camera.discovery import (
    configure_camera_performance,
    configure_rising_edge_triggers,
    open_camera_capture,
    rearm_camera_streams,
    shutdown_camera_streams,
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

    capture = open_camera_capture(dv)
    writer = None
    try:
        rearm_info = (
            rearm_camera_streams(capture) if getattr(args,
                                                     "camera_stream_rearm",
                                                     False) else None)
        configure_camera_performance(
            capture,
            bias_sensitivity=args.bias_sensitivity,
            efps=args.efps,
        )
        trigger_configuration = configure_rising_edge_triggers(capture)
        ready = validate_camera_ready(
            capture,
            stream_rearm=rearm_info,
            trigger_configuration=trigger_configuration,
        )
    except Exception:
        if getattr(args, "camera_shutdown_streams", False):
            shutdown_camera_streams(capture)
        del capture
        gc.collect()
        raise
    return capture, ready


def open_ready_camera_capture(args):
    capture = None
    try:
        capture, ready = _open_configured_camera_capture(args)
        initial_flush = flush_stale_batches(capture, reads=args.camera_flush_reads)
        ready = _ready_with_initial_flush(ready, initial_flush)
    except Exception:
        if capture is not None:
            if getattr(args, "camera_shutdown_streams", False):
                shutdown_camera_streams(capture)
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
            if getattr(args, "camera_shutdown_streams", False):
                shutdown_camera_streams(capture)
            del capture
        gc.collect()
        raise
    return capture, writer, ready


def close_camera_resources(resources, *, shutdown_streams):
    writer = resources.pop("writer", None)
    capture = resources.pop("capture", None)
    if writer is not None:
        del writer
    if capture is not None:
        if shutdown_streams:
            shutdown_camera_streams(capture)
        del capture
    gc.collect()
