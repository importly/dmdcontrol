import os
from typing import Optional, Tuple
import yaml
import numpy as np
from PIL import Image
import dv_processing as dv
from dmdcontrol.utils import WORKSPACE
from dmdcontrol.utils import Font

class BackgroundActivityNoiseFilter:
    """
    Python rewrite of the BackgroundActivityNoiseFilter from dv_processing. This tests the neighborhoods of incoming events for other supporting events that happened within the background activity period. If an event is supported by a neighbor, it is considered valid; otherwise, it is considered noise and filtered out.
    """
    
    def __init__(self, background_activity_duration: int = 2000, resolution_limits: Tuple[int, int] = (346, 260)):
        """
        Initiate a background activity noise filter, which tests the neighbourhoods of incoming events for other supporting events that happened within the background activity period.
        
        Args:
            background_activity_duration (int): Background activity duration in microseconds (default: 2000)
        
        Raises:
            ValueError: If background_activity_duration is less than 1
        """
        if background_activity_duration < 1:
            raise ValueError(f"background_activity_duration must be greater than 0, got {background_activity_duration}")
        
        self.resolution_limits = resolution_limits
        self.time_surface = np.zeros((self.resolution_limits[1], self.resolution_limits[0]), dtype=np.int64)
        self.background_activity_duration = background_activity_duration
    
    
    def _background_activity_lookup(self, x: int, y: int, timestamp: int) -> bool:
        """
        More efficient version of the background activity filter. Checks neighboring pixels for events that occurred within the background activity duration. Checks for corner cases and excludes the event itself from the neighborhood check.
        
        Args:
            x (int): X coordinate  
            y (int): Y coordinate  
            timestamp (int): Event timestamp
            
        Returns:
            True if event is supported by neighbors (valid), False otherwise (invalid)
        """
        # Exclude border regions
        y_start, y_end = max(0, y - 1), min(self.resolution_limits[1], y + 2)
        x_start, x_end = max(0, x - 1), min(self.resolution_limits[0], x + 2)
        
        # Extract neighborhood timestamps and compute differences
        neighborhood = self.time_surface[y_start:y_end, x_start:x_end]
        timestamp_diff = timestamp - neighborhood
        
        # Create mask excluding center pixel
        mask = np.ones_like(timestamp_diff, dtype=bool)
        mask[y - y_start, x - x_start] = False
    
        return np.any(timestamp_diff[mask] < self.background_activity_duration)
    
    
    def accept(self, events: np.ndarray) -> np.ndarray:
        """
        Accepts in a batch of events to be filterd. If difference between current timestamp and stored neighbor timestamp is smaller than given time limit, then it means the event is supported by a neighbor and thus valid. If it is bigger, then the event is not supported, and we need to check the next neighbor. If all are bigger, the event is invalid.
        
        Args:
            events (np.ndarray): Iterable of events
            
        Returns:
            np.ndarray: Filtered events
        """
        # Grab the event coordinates, timestamps, and polarities
        ts, xs, ys, ps = events[0], events[1], events[2], events[3]
        
        # Filter events
        mask = np.zeros(len(events[0]), dtype=bool)
        for i in range(len(events[0])):
            # Update mask
            mask[i] = self._background_activity_lookup(xs[i], ys[i], ts[i])
            
            # Update time surface
            self.time_surface[ys[i], xs[i]] = ts[i]
        filtered_events = events[mask]
        
        return filtered_events
    
    def reset(self):
        """Reset the time surface to zeros."""
        self.time_surface = np.zeros((self.resolution_limits[1], self.resolution_limits[0]), dtype=np.int64)
    

class Camera:
    """Class to control DAVIS346.

    Attributes:
        WIDTH (int): Width of the camera frame.
        HEIGHT (int): Height of the camera frame.
        camera: The camera object.
    """
    WIDTH = 346
    HEIGHT = 260
    
    def __init__(self, config: dict):
        """Class to control DAVIS346.

        Args:
            config (dict): configuration dictionary containing camera settings.
        """
        # Verbose?
        if config.get('verbose', True):
            self.verbose = True
            print(Font.VERBOSE)
            print('Printing verbose statements... Prepare to get wordy...')
            
        # Open camera
        self.camera = dv.io.camera.DAVIS()
        if self.verbose:
            print(Font.VERBOSE)
            print(f'Using {self.camera.getCameraName()}')
        
        # Configure camera settings
        # Events and frames
        self.camera.setEventsRunning(False)
        self.camera.setFramesRunning(False)
        
        # ROI
        self.roi_start_x = config.get('Camera', {}).get('ROI', {}).get('start_x', 0)
        self.roi_start_y = config.get('Camera', {}).get('ROI', {}).get('start_y', 0)
        self.ROI_WIDTH = config.get('Camera', {}).get('ROI', {}).get('width', 346)
        self.ROI_HEIGHT = config.get('Camera', {}).get('ROI', {}).get('height', 260)
        self.camera.setCropAreaEvents(
            self.roi_start_x,
            self.roi_start_y,
            self.ROI_WIDTH,
            self.ROI_HEIGHT
        )
        if self.verbose:
            print(Font.VERBOSE)
            print(
                f'ROI set. \n'
                f'{Font.BOLD} start_x: {Font.ENDC}{self.roi_start_x}, {Font.BOLD}width: {Font.ENDC}{self.ROI_WIDTH}\n'
                f'{Font.BOLD} start_y: {Font.ENDC}{self.roi_start_y}, {Font.BOLD}height: {Font.ENDC}{self.ROI_HEIGHT}{Font.ENDC}'
                )
        
        # Trigger
        self.camera.setDetectorRisingEdges(config.get('Camera', {}).get('Trigger', {}).get('rising_edge', True))
        self.camera.setDetectorFallingEdges(config.get('Camera', {}).get('Trigger', {}).get('falling_edge', False))
        self.camera.setDetectorRunning(False)
        
        # Filter
        if config.get('Camera', {}).get('Filter', {}).get('enable', True):
            self.filter = BackgroundActivityNoiseFilter(
                background_activity_duration=config.get('Camera', {}).get('Filter', {}).get('background_activity_duration', 2000),
                resolution_limits=(self.ROI_WIDTH, self.ROI_HEIGHT)
            )
            if self.verbose:
                print(Font.VERBOSE)
                print(f'Background activity noise filter enabled with duration {self.filter.background_activity_duration} \u03bcs')
        else:
            self.filter = None
            if self.verbose:
                print(Font.VERBOSE)
                print('Background activity noise filter disabled')

    def record(self, trigger_count: int) -> tuple:
        """Record event data for a set amount of triggers

        Args:
            trigger_count (int): The number of triggers to record.

        Returns:
            tuple: A tuple containing the triggers and events.
        """
        # Flush stale data from camera's buffers   
        if self.camera.isEventStreamAvailable():
            _ = self.camera.getNextEventBatch()
        if self.camera.isTriggerStreamAvailable():
            _ = self.camera.getNextTriggerBatch()
        
        # Enable events and external triggers
        self.camera.setDetectorRunning(True)
        self.camera.setEventsRunning(True)
        
        triggers = np.zeros((1,))
        events = np.zeros((3,))
        
        if self.verbose:
            print(Font.VERBOSE)
            print(f'Recording {trigger_count} triggers...')
            
        # Run loop until all data is collected
        while self.camera.isRunning() and len(triggers) <= trigger_count:
            # Read a batch of data from the camera
            event_batch = self.camera.getNextEventBatch()
            trigger_batch = self.camera.getNextTriggerBatch()
            
            # Check if there is valid data and if so, concatenate it
            if event_batch is not None and len(event_batch) > 0:
                events = np.concatenate((events, event_batch))
                
            if trigger_batch is not None and len(trigger_batch) > 0:
                triggers = np.concatenate((triggers, trigger_batch.timestamp))
            
        if self.verbose:
            print(Font.VERBOSE)
            print(
                f'Recording complete.\n'
                f'{Font.BOLD} Triggers:{Font.ENDC} {len(triggers)}\n'
                f'{Font.BOLD} Events:{Font.ENDC} {len(events)}'
                )
        return (triggers, events)
    
    def accumulate(self, triggers: np.ndarray, events: np.ndarray) -> np.ndarray:
        """Accumulate the recorded data into frames.

        Args:
            triggers (np.ndarray): _description_
            events (np.ndarray): _description_

        Returns:
            frames (np.ndarray): numpy array of shape (len(triggers), ROI_HEIGHT, ROI_WIDTH) containing the accumulated frames.
        """
        if self.verbose:
            print(Font.VERBOSE)
            print(f'Accumulating {len(events)} events into {len(triggers)} frames...')
            
        # Reset the filter if it exists
        if self.filter is not None:
            self.filter.reset()
            
        # Filter events
        events = self.filter.accept(events) if self.filter is not None else events
        
        # Slice up data between timestamps and accumulate
        frames = np.zeros((len(triggers), self.ROI_HEIGHT, self.ROI_WIDTH))
        for idx in range(len(triggers)):
            # Get the events that occurred between the current trigger and the next trigger
            event_slice = events[(events[:, 0] >= triggers[idx]) & (events[:, 0] < triggers[idx + 1])]
            
            # Accumulate the events into a frame
            for event in event_slice:
                x, y, polarity = event[1], event[2], event[3]
                frames[idx, y, x] += 1 if polarity else 0
                
        if self.verbose:
            print(Font.VERBOSE)
            print(
                'Accumulation complete.\n'
                f'{Font.BOLD} `frames` shape: {frames.shape}{Font.ENDC}'
                )
            
        return frames
    
    def save(self, frames: np.ndarray, folder: str, save_as_jpg: Optional[bool] = False):
        """
        Saves accumulated event frames to a folder.

        Args:
            frames (np.ndarray): A numpy array of shape (len(triggers), ROI_HEIGHT, ROI_WIDTH) containing the accumulated frames.
            folder (str): Folder to save to.
            save_as_jpg (Optional[bool], optional): Whether or not to save the frames as JPEG files. Defaults to False.
        """
        # Create the folder if it doesn't exist
        os.makedirs(folder, exist_ok=True)
        for frame in frames:
            # Save the frames to a .npy file
            np.save(f"{folder}/frame_{frames.index(frame)}.npy", frame)
            
            # Save the frames to a .jpg file
            if save_as_jpg:
                frame = (frame / np.max(frame) * 255).astype(np.uint8)
                Image.fromarray(frame).save(f"{folder}/frame_{frames.index(frame)}.jpg")
        
        if self.verbose:
            print(Font.VERBOSE)
            print(f'Saved {len(frames)} frames to {folder}')

Camera({})