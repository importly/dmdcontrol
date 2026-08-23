import os
import logging
import time
from typing import Optional, Tuple
from pathlib import Path
import numpy as np
from PIL import Image
import dv_processing as dv
from dmdcontrol.utils import Font, CONFIG

ROI_WIDTH = CONFIG.get('Camera', {}).get('ROI', {}).get('width', CONFIG.get('Camera', {}).get('width', 346))
ROI_HEIGHT = CONFIG.get('Camera', {}).get('ROI', {}).get('height', CONFIG.get('Camera', {}).get('height', 260))

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
        self.logger = logging.getLogger('Filter')
        
        if background_activity_duration < 1:
            raise ValueError(f"background_activity_duration must be greater than 0, got {background_activity_duration}")
        
        self.resolution_limits = resolution_limits
        self.time_surface = np.zeros((self.resolution_limits[1], self.resolution_limits[0]), dtype=np.int64)
        self.background_activity_duration = background_activity_duration
    
    def _background_activity_lookup(self, x: int, y: int, timestamp: int) -> np.bool_:
        """
        More efficient version of the background activity filter. Checks neighboring pixels for events that occurred within the background activity duration. Checks for corner cases and excludes the event itself from the neighborhood check.
        
        Args:
            x (int): X coordinate  
            y (int): Y coordinate  
            timestamp (int): Event timestamp
            
        Returns:
            np.bool_: True if event is supported by neighbors (valid), False otherwise (invalid)
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
        ts, xs, ys = events['timestamp'], events['x'], events['y']
        
        # Filter events
        mask = np.zeros(events.shape[0], dtype=bool)
        for i in range(events.shape[0]):
            # Update mask
            mask[i] = self._background_activity_lookup(xs[i], ys[i], ts[i])
            
            # Update time surface
            self.time_surface[ys[i], xs[i]] = ts[i]
        # self.logger.info('Filtered %s events out of %s', np.sum(~mask), len(events[0]))
        # self.logger.info('events shape: %s, mask shape: %s', events.shape, mask.shape)
        filtered_events = events[mask]
        
        return filtered_events
    
    def reset(self):
        """Reset the time surface to zeros."""
        self.time_surface = np.zeros((self.resolution_limits[1], self.resolution_limits[0]), dtype=np.int64)
    

class Camera:
    """
    Class to control DAVIS346.
    """
    
    def __init__(self):
        """
        Initialize the Camera class.
        
        Raises:
            ValueError: If the ROI exceeds the camera resolution.
        """
        # Set up logging
        self.logger = logging.getLogger('Camera')
        
        # Open camera
        self.camera = dv.io.camera.DAVIS()
        self.logger.info('Using %s camera', self.camera.getCameraName())
        
        # Configure camera settings
        # Events and frames
        self.camera.setEventsRunning(False)
        self.camera.setFramesRunning(False)
        
        # ROI
        self.roi_start_x = CONFIG.get('Camera', {}).get('ROI', {}).get('start_x', 0)
        self.roi_start_y = CONFIG.get('Camera', {}).get('ROI', {}).get('start_y', 0)
        self.WIDTH = CONFIG.get('Camera', {}).get('width', 346)
        self.HEIGHT = CONFIG.get('Camera', {}).get('height', 260)
        self.roi_end_x = self.roi_start_x + ROI_WIDTH
        self.roi_end_y = self.roi_start_y + ROI_HEIGHT
        # Error checking for ROI exceeding camera resolution
        if (self.roi_start_x + ROI_WIDTH > self.WIDTH) or (self.roi_start_y + ROI_HEIGHT > self.HEIGHT):
            self.logger.error(f"ROI exceeds camera resolution. ROI: ({self.roi_start_x}, {self.roi_start_y}, {ROI_WIDTH}, {ROI_HEIGHT}), Camera Resolution: ({self.WIDTH}, {self.HEIGHT})")
            raise ValueError(f"ROI exceeds camera resolution. ROI: ({self.roi_start_x}, {self.roi_start_y}, {ROI_WIDTH}, {ROI_HEIGHT}), Camera Resolution: ({self.WIDTH}, {self.HEIGHT})")
        roi = self.camera.getCropArea()
        self.logger.info(f'ROI set. \n {Font.BOLD}start_x:{Font.ENDC} %s, {Font.BOLD}width:{Font.ENDC} %s\n {Font.BOLD} start_y:{Font.ENDC} %s, {Font.BOLD}height:{Font.ENDC} %s{Font.ENDC}', self.roi_start_x, ROI_WIDTH, self.roi_start_y, ROI_HEIGHT)
        
        # Trigger
        self.camera.setDetectorRisingEdges(CONFIG.get('Camera', {}).get('Trigger', {}).get('rising_edge', True))
        self.camera.setDetectorFallingEdges(CONFIG.get('Camera', {}).get('Trigger', {}).get('falling_edge', False))
        self.camera.setDetectorRunning(False)
        
        # Filter
        if CONFIG.get('Camera', {}).get('Filter', {}).get('enable', True):
            self.filter = BackgroundActivityNoiseFilter(
                background_activity_duration=CONFIG.get('Camera', {}).get('Filter', {}).get('background_activity_duration', 2000),
                resolution_limits=(self.WIDTH, self.HEIGHT)
            )
            self.logger.info('Background activity noise filter enabled with duration %s \u03bcs', self.filter.background_activity_duration)
        else:
            self.filter = None
            self.logger.info('Background activity noise filter disabled')
                
        # Accumulation
        self.window_us = CONFIG.get('Camera', {}).get('Accumulation', {}).get('window_us', 16666)
        self.offset_us = CONFIG.get('Camera', {}).get('Accumulation', {}).get('start_time_offset_us', 0)
        self.logger.info(f'Accumulation settings:\n {Font.BOLD}Time window (\u03bcs):{Font.ENDC} %s\n {Font.BOLD} Start time offset (\u03bcs):{Font.ENDC} %s', self.window_us, self.offset_us)
        
        # Enable events and external triggers
        self.camera.setDetectorRunning(True)
        self.camera.setEventsRunning(True)

    def flush(self):
        """
        Flush stale data.
        """
        # Flush stale data from camera's buffers   
        if self.camera.isEventStreamAvailable():
            _ = self.camera.getNextEventBatch()
        if self.camera.isTriggerStreamAvailable():
            _ = self.camera.getNextTriggerBatch()
            
    def record(self, trigger_count: int) -> tuple:
        """Record event data for a set amount of triggers

        Args:
            trigger_count (int): The number of triggers to record.

        Returns:
            tuple: A tuple containing the triggers and events.
        """
            
        triggers = np.zeros((trigger_count,))
        trigger_index = 0
        event_batches = []
        
        self.logger.info('Recording %s triggers...', trigger_count)
            
        # Run loop until all data is collected
        while self.camera.isRunning() and trigger_index < trigger_count:
            # Read a batch of data from the camera
            event_batch = self.camera.getNextEventBatch()
            trigger_batch = self.camera.getNextTriggerBatch()
            
            # Check if there is valid data and if so, append it
            if event_batch is not None:
                event_batches.append(event_batch.numpy())
                
            if trigger_batch is not None:
                while len(trigger_batch) > 0:
                    trigger = trigger_batch.pop()
                    if int(trigger.type) == 1:
                        # dont comment this out its a load bearing line of code YOU WILL DROP FRAMES IF THIS IS COMMENTED OUT IDK WHY BUT YOU WILL DONT DO IT
                        self.logger.info('Trigger type: %s', trigger.type) 
                        triggers[trigger_index] = trigger.timestamp
                        trigger_index += 1
            
            time.sleep(0.0001)
        
        # Get potentially remaining data after the loop ends
        while True:
            event_batch = self.camera.getNextEventBatch()
            if event_batch is not None:
                event_batches.append(event_batch.numpy())
                if event_batches[-1][-1]['timestamp'] > triggers[-1] + self.window_us:
                    break
        
        # Concatenate all batches at once
        events = np.concatenate(event_batches, dtype=[('timestamp', '<i8'), ('x', '<i2'), ('y', '<i2'), ('polarity', 'i1')])
        self.logger.info(f'Recording complete.\n {Font.BOLD}Triggers:{Font.ENDC} %s\n {Font.BOLD}Events:{Font.ENDC} %s', len(triggers), len(events))
        return (triggers, events)
    
    def accumulate(self, triggers: np.ndarray, events: np.ndarray, frame_count: int) -> np.ndarray:
        """Accumulate the recorded data into frames.

        Args:
            triggers (np.ndarray): _description_
            events (np.ndarray): _description_

        Returns:
            frames (np.ndarray): numpy array of shape (len(triggers), ROI_HEIGHT, ROI_WIDTH) containing the accumulated frames.
        """
        self.logger.info('Accumulating %s events into %s frames...', len(events), len(triggers))
            
        # Reset the filter if it exists
        if self.filter is not None:
            self.filter.reset()
            
        # Filter events
        events = self.filter.accept(events) if self.filter is not None else events
        
        index_test = np.zeros((13,), dtype=np.uint32)
        for idx in range(13):
            index_test[idx] = self._accumulate_total(events, triggers[idx]) if self._accumulate_total(events, triggers[idx]) is not None else 0 # pyright: ignore
        start_diff = np.gradient(index_test)
        first_frame_idx = np.argmax(start_diff[8:11]) + 8 + 1
        
        # Slice up data between timestamps and accumulate
        frames = np.zeros((frame_count, ROI_HEIGHT, ROI_WIDTH), dtype=np.uint32)
        for idx in range(frame_count):
            frame = self._accumulate_frame(events, triggers[2*idx+first_frame_idx])
            
            if frame is not None:
                frames[idx] = np.histogram2d(
                    frame[1],
                    frame[0],
                    bins=(ROI_HEIGHT, ROI_WIDTH),
                    weights=frame[2],
                )[0].astype(np.uint32)
            else:
                self.logger.warning('No events found for frame %s. Frame will be empty.', 2*idx+first_frame_idx)
            
        self.logger.info(f'Accumulation complete.\n `frames` shape: %s', frames.shape)
            
        return frames
    
    def _accumulate_frame(self, events: np.ndarray, trigger: int) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
            start_time = trigger + self.offset_us
            end_time = start_time + self.window_us
            
            # Clip to window size and ROI
            event_slice = events[
                (events[:]['timestamp'] >= start_time) &
                (events[:]['timestamp'] < end_time) 
            ]
            event_slice = event_slice[
                (event_slice['x'] >= self.roi_start_x) & (event_slice['y'] >= self.roi_start_y) &
                (event_slice['x'] < self.roi_end_x) & (event_slice['y'] < self.roi_end_y)
            ]
            
            # Accumulate events into frames
            if len(event_slice) > 0:
                # Offset the event coordinates to the ROI
                event_slice['x'] -= self.roi_start_x
                event_slice['y'] -= self.roi_start_y
                
                # Get locs of positive events
                locs = np.where(event_slice['polarity'], 1, 0).astype(np.uint32)
                return event_slice['x'], event_slice['y'], locs
                
            else:
                return None
            
    def _accumulate_total(self, events: np.ndarray, trigger: int) -> np.uint32 | None:
            start_time = trigger + self.offset_us
            end_time = start_time + self.window_us
            
            # Clip to window size and ROI
            event_slice = events[
                (events[:]['timestamp'] >= start_time) &
                (events[:]['timestamp'] < end_time) 
            ]
            event_slice = event_slice[
                (event_slice['x'] >= self.roi_start_x) & (event_slice['y'] >= self.roi_start_y) &
                (event_slice['x'] < self.roi_end_x) & (event_slice['y'] < self.roi_end_y)
            ]
            
            # Accumulate events into frames
            if len(event_slice) > 0:
                # Get locs of positive events
                locs = np.where(event_slice['polarity'], 1, 0).astype(np.uint32)
                return np.sum(locs)
                
            else:
                return None
    
    def save(self, frames: np.ndarray, folder: Path, save_as_img: Optional[bool] = False):
        """
        Saves accumulated event frames to a folder.

        Args:
            frames (np.ndarray): A numpy array of shape (len(triggers), ROI_HEIGHT, ROI_WIDTH) containing the accumulated frames.
            folder (str): Folder to save to.
            save_as_img (Optional[bool], optional): Whether or not to save the frames as image files. Defaults to False.
        """
        # Create the folder if it doesn't exist
        os.makedirs(folder, exist_ok=True)
        for idx, frame in enumerate(frames):
            if save_as_img:
                # Save the frames to a .png file
                frame = (frame / np.max(frame) * 255).astype(np.uint8)
                Image.fromarray(frame, mode='L').save(f'{folder}/frame_{idx}.png')
            else:
                # Save the frames to a .npy file
                np.save(f'{folder}/frame_{idx}.npy', frame)
        
        self.logger.info('Saved %s frames to %s', len(frames), folder)
        
        
def contact_sheet(
    frames: np.ndarray, 
    save_path: Path = Path('./contact_sheet.jpg'), 
    grid_size: Tuple[int, int] = (20, 10),
):
    """
    Creates a contact sheet of the accumulated event frames and saves it to a file.

    Args:
        frames (np.ndarray): A numpy array of shape (len(triggers), ROI_HEIGHT, ROI_WIDTH) containing the accumulated frames.
        folder (Path): Folder to save the contact sheet to.
        grid_size (Tuple[int, int], optional): Size of the grid for the contact sheet. Defaults to (20, 10).
        file_name (Path, optional): Name of the file to save the contact sheet to. Defaults to 'contact_sheet.jpg'.
    """
    # Create a blank canvas for the contact sheet
    contact_sheet = Image.new('L', (ROI_WIDTH * grid_size[0], ROI_HEIGHT * grid_size[1]))
    
    for idx, frame in enumerate(frames):
        if idx >= grid_size[0] * grid_size[1]:
            break
        # Normalize and convert frame to image
        frame_img = Image.fromarray(((frame - np.min(frame)) / (np.max(frame) - np.min(frame)) * 255).astype(np.uint8), mode='L')
        x_offset = (idx % grid_size[0]) * ROI_WIDTH
        y_offset = (idx // grid_size[0]) * ROI_HEIGHT
        contact_sheet.paste(frame_img, (x_offset, y_offset))
    
    # Save the contact sheet
    contact_sheet.save(save_path)

