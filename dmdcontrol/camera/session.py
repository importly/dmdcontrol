from __future__ import annotations

import gc
import json
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


def _print_camera_configuration(capture, args):
    readback = {}
    for method_name in sorted(dir(capture)):
        if not method_name.startswith(("get", "is")) or method_name.startswith("getNext"):
            continue
        try:
            method = getattr(capture, method_name)
            if not callable(method):
                continue
            readback[method_name] = method()
        except TypeError:
            # Getter requires arguments, so it cannot be safely included automatically.
            continue
        except Exception as exc:
            readback[method_name] = f"<{type(exc).__name__}: {exc}>"

    print("=== Camera configuration (temporary diagnostic) ===")
    print(
        json.dumps(
            {
                "requested": vars(args),
                "readback": readback,
            },
            indent=2,
            sort_keys=True,
            default=str,
        ))


def open_ready_camera(run, args):
    capture = None
    writer = None
    try:
        capture, ready = _open_configured_camera_capture(args)
        writer = open_camera_writer(run, capture)
        initial_flush = flush_stale_batches(capture, reads=args.camera_flush_reads)
        ready = _ready_with_initial_flush(ready, initial_flush)
        # _print_camera_configuration(capture, args)
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
