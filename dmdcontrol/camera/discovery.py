from __future__ import annotations

import time

from dmdcontrol.support.constants import (
    DVXPLORER_CONTRAST_THRESHOLDS,
    DVXPLORER_READOUT_FPS_NAMES,
)

def descriptor_to_dict(index, descriptor):
    return {
        "index": index,
        "repr": repr(descriptor),
        "devAddress": getattr(descriptor, "devAddress", None),
        "deviceType": str(getattr(descriptor, "deviceType", None)),
        "cameraModel": str(getattr(descriptor, "cameraModel", None)),
        "firmwareVersion": str(getattr(descriptor, "firmwareVersion", None)),
        "serialNumber": str(getattr(descriptor, "serialNumber", None)),
    }


def discover_cameras():
    import dv_processing as dv
    cameras = dv.io.camera.discover()
    return [
        descriptor_to_dict(index, descriptor)
        for index, descriptor in enumerate(cameras)
    ]


def _call_if_available(capture, method_name, *args):
    method = getattr(capture, method_name, None)
    if not callable(method):
        return False
    method(*args)
    return True


def _drain_camera_batches(capture, reads):
    for _ in range(max(0, int(reads))):
        if hasattr(capture, "getNextEventBatch"):
            capture.getNextEventBatch()
        if hasattr(capture, "getNextTriggerBatch"):
            capture.getNextTriggerBatch()


def rearm_camera_streams(capture, settle_s=0.05, drain_reads=10):
    stopped_events = _call_if_available(capture, "setEventsRunning", False)
    stopped_detector = _call_if_available(capture, "setDetectorRunning", False)
    stopped_generator = _call_if_available(capture, "setGeneratorRunning", False)
    if settle_s > 0:
        time.sleep(settle_s)
    started_events = _call_if_available(capture, "setEventsRunning", True)
    _drain_camera_batches(capture, drain_reads)
    return {
        "stopped_events": stopped_events,
        "stopped_detector": stopped_detector,
        "stopped_generator": stopped_generator,
        "started_events": started_events,
        "drain_reads": int(drain_reads),
    }


def shutdown_camera_streams(capture):
    errors = []

    def _stop(method_name):
        try:
            return _call_if_available(capture, method_name, False)
        except Exception as exc:
            errors.append(f"{method_name}: {exc!r}")
            return False

    return {
        "stopped_events": _stop("setEventsRunning"),
        "stopped_detector": _stop("setDetectorRunning"),
        "stopped_generator": _stop("setGeneratorRunning"),
        "errors": errors,
    }


def configure_rising_edge_triggers(capture):
    if hasattr(capture, "setDetectorRisingEdges"):
        capture.setDetectorRisingEdges(True)
    if hasattr(capture, "setDetectorFallingEdges"):
        capture.setDetectorFallingEdges(False)
    if hasattr(capture, "setDetectorRunning"):
        capture.setDetectorRunning(True)


def configure_camera_performance(capture, bias_sensitivity=None, efps=None):
    if bias_sensitivity is not None and bias_sensitivity != "default":
        configured = _configure_dvxplorer_contrast_thresholds(capture, bias_sensitivity)
        if not configured:
            _configure_legacy_dvs_bias_sensitivity(capture, bias_sensitivity)

    if efps is not None and efps != "default":
        configured = _configure_dvxplorer_readout_fps(capture, efps)
        if not configured:
            _configure_legacy_dvxplorer_efps(capture, efps)


def _configure_dvxplorer_contrast_thresholds(capture, bias_sensitivity):
    threshold = DVXPLORER_CONTRAST_THRESHOLDS.get(bias_sensitivity.lower())
    if threshold is None:
        return False
    if not (
            hasattr(capture, "setContrastThresholdOn")
            and hasattr(capture, "setContrastThresholdOff")
    ):
        return False
    capture.setContrastThresholdOn(threshold)
    capture.setContrastThresholdOff(threshold)
    return True


def _configure_dvxplorer_readout_fps(capture, efps):
    if not hasattr(capture, "setReadoutFPS"):
        return False
    readout_name = DVXPLORER_READOUT_FPS_NAMES.get(efps.lower())
    if readout_name is None:
        return False
    import dv_processing as dv
    readout_fps = getattr(getattr(dv.io.camera, "DVXplorer", None), "ReadoutFPS", None)
    value = getattr(readout_fps, readout_name, None) if readout_fps is not None else None
    if value is None:
        return False
    capture.setReadoutFPS(value)
    return True


def _configure_legacy_dvs_bias_sensitivity(capture, bias_sensitivity):
    if not hasattr(capture, "setDVSBiasSensitivity"):
        return False
    import dv_processing as dv
    bias = getattr(getattr(dv.io, "CameraCapture", None), "BiasSensitivity", None)
    mapping = {
        "verylow": getattr(bias, "VeryLow", None),
        "low": getattr(bias, "Low", None),
        "high": getattr(bias, "High", None),
        "veryhigh": getattr(bias, "VeryHigh", None),
    }
    value = mapping.get(bias_sensitivity.lower())
    if value is None:
        return False
    capture.setDVSBiasSensitivity(value)
    return True


def _configure_legacy_dvxplorer_efps(capture, efps):
    if not hasattr(capture, "setDVXplorerEFPS"):
        return False
    import dv_processing as dv
    efps_enum = getattr(getattr(dv.io, "CameraCapture", None), "DVXeFPS", None)
    mapping = {
        "variable": getattr(efps_enum, "EFPS_VARIABLE", None),
        "variable_5000": getattr(efps_enum, "EFPS_VARIABLE_5000", None),
        "constant_1000": getattr(efps_enum, "EFPS_CONSTANT_1000", None),
        "constant_100": getattr(efps_enum, "EFPS_CONSTANT_100", None),
    }
    value = mapping.get(efps.lower())
    if value is None:
        return False
    capture.setDVXplorerEFPS(value)
    return True


def capability_dict(capture):
    payload = {
        "name": capture.getCameraName() if hasattr(capture, "getCameraName") else None
    }
    for key, method_name in (
            ("event_stream", "isEventStreamAvailable"),
            ("frame_stream", "isFrameStreamAvailable"),
            ("imu_stream", "isImuStreamAvailable"),
            ("trigger_stream", "isTriggerStreamAvailable"),
    ):
        payload[key] = (
            bool(getattr(capture, method_name)())
            if hasattr(capture, method_name)
            else None
        )
    if hasattr(capture, "getEventResolution") and payload["event_stream"]:
        payload["event_resolution"] = tuple(capture.getEventResolution())
    if hasattr(capture, "getFrameResolution") and payload["frame_stream"]:
        payload["frame_resolution"] = tuple(capture.getFrameResolution())
    return payload


def camera_status():
    import dv_processing as dv
    discovered = discover_cameras()
    capture = dv.io.camera.open()
    try:
        configure_rising_edge_triggers(capture)
        return {"discovered": discovered, "opened": capability_dict(capture)}
    finally:
        del capture
