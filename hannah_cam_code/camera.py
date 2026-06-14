import os
import threading
from datetime import datetime, timedelta
import yaml
import json
import dv_processing as dv
import xml.etree.ElementTree as ET
from utils.env import WORKSPACE


class Camera:

    def __init__(self):
        # get cofiguration
        with open('config/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        self._capture_thread = threading.Thread(target=self._capture_loop)
        self._stop_event = threading.Event()

        # set output path
        if 'output_folder' not in config:
            raise ValueError('output_folder not specified in config.yaml')
        self.filename = (
            WORKSPACE / config['output_folder'] / datetime.now().strftime("%Y-%m-%d_%H-%M-%S") /
            'recording.aedat4')
        os.makedirs(self.filename.parent, exist_ok=True)

        # open camera
        self.camera = dv.io.camera.open()

        # make sure camera settings are the same
        if 'camera' not in config:
            raise ValueError('camera not specified in config.yaml')

        # CF = dv.io.camera.DAVIS.Davis346BiasCF
        # self.camera.setDavis346BiasCoarseFine(CF.Diff, 4, 67)
        # self.camera.setDavis346BiasCoarseFine(CF.On,   7, 40)
        # self.camera.setDavis346BiasCoarseFine(CF.Off,  3,  5)
        # self.camera.setBackgroundActivityFilter(221)

    def record(self):
        # Check if camera is already recording
        if self._capture_thread.is_alive():
            print("Camera is already recording")
            return
        # Start threaded capture
        self._stop_event.clear()
        self._capture_thread.start()

    def stop(self):
        print("Stop recording")
        self._stop_event.set()
        self._capture_thread.join(timeout=5)
        if self._capture_thread.is_alive():
            print("Warning: capture thread did not stop within timeout")

    def _capture_loop(self):
        writer = dv.io.MonoCameraWriter(str(self.filename), self.camera, dv.CompressionType.LZ4)
        print("Start recording")
        while self.camera.isRunning() and not self._stop_event.is_set():
            if self.camera.isEventStreamAvailable():
                events = self.camera.getNextEventBatch()
                if events is not None:
                    writer.writeEvents(events, streamName="events")
