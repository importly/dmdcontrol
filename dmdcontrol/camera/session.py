from __future__ import annotations

import gc
import os

from dmdcontrol.camera.capture import flush_stale_batches, validate_camera_ready
from dmdcontrol.camera.discovery import (
    configure_camera_performance,
    configure_rising_edge_triggers,
    open_camera_capture,
    rearm_camera_streams,
    shutdown_camera_streams,
)
from dmdcontrol.camera.usb_reset import reset_camera_usb, run_power_cycle_command


def _open_configured_camera_capture(args):
    import dv_processing as dv

    power_cycle_command = args.camera_power_cycle_command or os.environ.get("DMD_CAMERA_POWER_CYCLE_COMMAND")
    power_cycle_info = run_power_cycle_command(power_cycle_command)
    usb_reset_info = reset_camera_usb(dv, enabled=args.camera_usb_reset)
    camera_open_method = getattr(args, "camera_open_method", "modern")
    capture = open_camera_capture(dv, method=camera_open_method)
    writer = None
    try:
        rearm_info = (
            rearm_camera_streams(capture)
            if getattr(args, "camera_stream_rearm", False)
            else None
        )
        configure_camera_performance(
            capture,
            bias_sensitivity=args.bias_sensitivity,
            efps=args.efps,
            prefer_legacy=(camera_open_method == "legacy"),
        )
        configure_rising_edge_triggers(capture)
        ready = validate_camera_ready(
            capture,
            stream_rearm=rearm_info,
            usb_reset=usb_reset_info,
            power_cycle=power_cycle_info,
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
        flush_stale_batches(capture, reads=args.camera_flush_reads)
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
        flush_stale_batches(capture, reads=args.camera_flush_reads)
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
