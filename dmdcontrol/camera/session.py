from __future__ import annotations

import gc
from dataclasses import is_dataclass, replace
from typing import Any, cast

from dmdcontrol.camera.capture import flush_stale_batches, validate_camera_ready
from dmdcontrol.camera.discovery import (
    configure_camera_performance,
    configure_rising_edge_triggers,
    open_camera_capture,
)

_CAMERA_READBACK_METHODS = (
    "getCameraName",
    "getContrastThresholdOn",
    "getContrastThresholdOff",
    "getReadoutFPS",
    "getGlobalHold",
    "getGlobalReset",
)


def _ready_with_initial_flush(ready, initial_flush):
    if not isinstance(ready, type) and is_dataclass(ready):
        return replace(cast(Any, ready), initial_flush=initial_flush)
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
        performance_configuration = configure_camera_performance(
            capture,
            bias_sensitivity=args.bias_sensitivity,
            efps=args.efps,
            global_hold=getattr(args,
                                "camera_global_hold",
                                "default"),
        )
        camera_configuration = _camera_configuration_snapshot(
            capture,
            performance_configuration,
        )
        trigger_configuration = configure_rising_edge_triggers(capture)
        ready = validate_camera_ready(
            capture,
            stream_rearm=None,
            trigger_configuration=trigger_configuration,
            camera_configuration=camera_configuration,
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


def open_full_camera_writer(run, capture):
    import dv_processing as dv

    return dv.io.MonoCameraWriter(str(run.raw_full_recording_path), capture)


def _metadata_value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_metadata_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _metadata_value(item) for key, item in value.items()}
    return str(value)


def _camera_configuration_snapshot(capture, performance_configuration):
    readback = {}
    readback_errors = {}
    for method_name in _CAMERA_READBACK_METHODS:
        method = getattr(capture, method_name, None)
        if not callable(method):
            continue
        try:
            readback[method_name] = _metadata_value(method())
        except Exception as exc:
            readback_errors[method_name] = repr(exc)

    snapshot = {
        "requested": performance_configuration["requested"],
        "applied": performance_configuration["applied"],
        "readback": readback,
    }
    if readback_errors:
        snapshot["readback_errors"] = readback_errors
    return snapshot


def _open_ready_camera(run, args, *, include_full_recording):
    capture = None
    writer = None
    full_writer = None
    try:
        capture, ready = _open_configured_camera_capture(args)
        writer = open_camera_writer(run, capture)
        if include_full_recording:
            full_writer = open_full_camera_writer(run, capture)
        initial_flush = flush_stale_batches(
            capture,
            reads=args.camera_flush_reads,
            archive_writer=full_writer,
        )
        if full_writer is not None:
            initial_flush["archived_to"] = run.raw_full_recording_path.name
        ready = _ready_with_initial_flush(ready, initial_flush)
    except Exception:
        if writer is not None:
            del writer
        if full_writer is not None:
            del full_writer
        if capture is not None:
            del capture
        gc.collect()
        raise
    return capture, writer, ready, full_writer


def open_ready_camera(run, args):
    capture, writer, ready, _ = _open_ready_camera(
        run,
        args,
        include_full_recording=False,
    )
    return capture, writer, ready


def open_ready_camera_with_full_recording(run, args):
    return _open_ready_camera(
        run,
        args,
        include_full_recording=True,
    )


def close_camera_resources(resources):
    writer = resources.pop("writer", None)
    full_writer = resources.pop("full_writer", None)
    capture = resources.pop("capture", None)
    if writer is not None:
        del writer
    if full_writer is not None:
        del full_writer
    if capture is not None:
        del capture
    gc.collect()
