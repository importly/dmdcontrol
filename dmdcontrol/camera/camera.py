import os
import time
import logging
from typing import Any, Optional, Tuple
from pathlib import Path
import numpy as np
from PIL import Image
import dv_processing as dv
try:
    from metavision_hal import I_TriggerIn, I_ROI  # type: ignore
    from metavision_sdk_stream import (  # type: ignore
        Camera as MetavisionCamera,
        CameraStreamSlicer,
        SliceCondition,
    )
except ImportError:
    I_TriggerIn: Any = None
    I_ROI: Any = None
    MetavisionCamera: Any = None
    CameraStreamSlicer: Any = None
    SliceCondition: Any = None
from dmdcontrol.utils import Font, CONFIG

EVENT_DTYPE = np.dtype([('timestamp', '<i8'), ('x', '<i2'), ('y', '<i2'), ('polarity', 'i1')])

CONTRAST_THRESHOLDS = {'verylow': 15, 'low': 12, 'high': 6, 'veryhigh': 3}  # 'default' is 9


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
    

class CameraDAVIS:
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
        self.ROI_WIDTH = CONFIG.get('Camera', {}).get('ROI', {}).get('width', CONFIG.get('Camera', {}).get('width', 346))
        self.ROI_HEIGHT = CONFIG.get('Camera', {}).get('ROI', {}).get('height', CONFIG.get('Camera', {}).get('height', 260))
        # Error checking for ROI exceeding camera resolution
        if (self.roi_start_x + self.ROI_WIDTH > self.WIDTH) or (self.roi_start_y + self.ROI_HEIGHT > self.HEIGHT):
            self.logger.error(f"ROI exceeds camera resolution. ROI: ({self.roi_start_x}, {self.roi_start_y}, {self.ROI_WIDTH}, {self.ROI_HEIGHT}), Camera Resolution: ({self.WIDTH}, {self.HEIGHT})")
            raise ValueError(f"ROI exceeds camera resolution. ROI: ({self.roi_start_x}, {self.roi_start_y}, {self.ROI_WIDTH}, {self.ROI_HEIGHT}), Camera Resolution: ({self.WIDTH}, {self.HEIGHT})")
        self.camera.setCropAreaEvents(
            (
                self.roi_start_x,
                self.roi_start_y,
                self.ROI_WIDTH,
                self.ROI_HEIGHT
            )
        )
        self.logger.info(f'ROI set. \n {Font.BOLD}start_x:{Font.ENDC} %s, {Font.BOLD}width:{Font.ENDC} %s\n {Font.BOLD} start_y:{Font.ENDC} %s, {Font.BOLD}height:{Font.ENDC} %s{Font.ENDC}', self.roi_start_x, self.ROI_WIDTH, self.roi_start_y, self.ROI_HEIGHT)
        
        # Trigger
        self.camera.setDetectorRisingEdges(CONFIG.get('Camera', {}).get('Trigger', {}).get('rising_edge', True))
        self.camera.setDetectorFallingEdges(CONFIG.get('Camera', {}).get('Trigger', {}).get('falling_edge', False))
        self.camera.setDetectorRunning(False)
        
        # Filter
        if CONFIG.get('Camera', {}).get('Filter', {}).get('enable', True):
            self.filter = BackgroundActivityNoiseFilter(
                background_activity_duration=CONFIG.get('Camera', {}).get('Filter', {}).get('background_activity_duration', 2000),
                resolution_limits=(self.ROI_WIDTH, self.ROI_HEIGHT)
            )
            self.logger.info('Background activity noise filter enabled with duration %s \u03bcs', self.filter.background_activity_duration)
        else:
            self.filter = None
            self.logger.info('Background activity noise filter disabled')
                
        # Accumulation
        self.window_us = CONFIG.get('Camera', {}).get('Accumulation', {}).get('window_us', 16666)
        self.offset_us = CONFIG.get('Camera', {}).get('Accumulation', {}).get('start_time_offset_us', 0)
        self.logger.info(f'Accumulation settings:\n {Font.BOLD}Time window (\u03bcs):{Font.ENDC} %s\n {Font.BOLD} Start time offset (\u03bcs):{Font.ENDC} %s', self.window_us, self.offset_us)
        
        
        self.normalize_scale_max = CONFIG.get('Camera', {}).get('normalize_scale_max', 255)
        self.signal_fraction = CONFIG.get('Camera', {}).get('signal_fraction', 0.1)
        
        self._apply_bias_sensitivity(CONFIG.get('Camera', {}).get('bias_sensitivity', 'default'))
        
        # Enable events and external triggers
        self.camera.setDetectorRunning(True)
        self.camera.setEventsRunning(True)

    def _apply_bias_sensitivity(self, preset: str) -> None:
        """Set the DVS contrast threshold, as master's --bias-sensitivity does.

        The default threshold fires on low-contrast scatter, which floods the
        sensor with one-event-per-pixel noise and buries the pattern.
        """
        threshold = CONTRAST_THRESHOLDS.get(str(preset).lower())
        if threshold is None:
            self.logger.info('Bias sensitivity left at camera default')
            return
        set_on = getattr(self.camera, 'setContrastThresholdOn', None)
        set_off = getattr(self.camera, 'setContrastThresholdOff', None)
        if not (callable(set_on) and callable(set_off)):
            self.logger.warning('Camera does not expose contrast thresholds; '
                                'bias_sensitivity=%s not applied', preset)
            return
        set_on(threshold)
        set_off(threshold)
        self.logger.info('Bias sensitivity %s: contrast threshold %s', preset, threshold)

    def flush(self, flush_count: int):
        """
        Flush stale data.
        """
        e_discarded = 0
        t_discarded = 0
        e_check = False
        t_check = False

        for _ in range(flush_count):
            e_check = False
            t_check = False

            if self.camera.isEventStreamAvailable():
                e_check = self.camera.getNextEventBatch() is not None
            if self.camera.isTriggerStreamAvailable():
                t_check = self.camera.getNextTriggerBatch() is not None

            if e_check:
                e_discarded += 1
            if t_check:
                t_discarded += 1

            if not e_check and not t_check:
                break

        self.logger.info('Flushed %s event batches and %s trigger batches', e_discarded, t_discarded)


    def record(self, trigger_count: int) -> tuple:
        """Record event data for a set amount of triggers

        Args:
            trigger_count (int): The number of triggers to record.

        Returns:
            tuple: A tuple containing the triggers and events.
        """
            
        triggers = np.zeros((trigger_count,))
        trigger_index = 0
        events = np.zeros((1,), dtype=[('timestamp', '<i8'), ('x', '<i2'), ('y', '<i2'), ('polarity', 'i1')])
        
        self.logger.info('Recording %s triggers...', trigger_count)
            
        # Run loop until all data is collected
        while self.camera.isRunning() and trigger_index < trigger_count:
            # Read a batch of data from the camera
            event_batch = self.camera.getNextEventBatch()
            trigger_batch = self.camera.getNextTriggerBatch()
            
            # Check if there is valid data and if so, concatenate it
            if event_batch is not None:
                events = np.concatenate((events, event_batch.numpy()))
                
            if trigger_batch is not None:
                while len(trigger_batch) > 0:
                    trigger = trigger_batch.pop()
                    if int(trigger.type) == 1:
                        # dont comment this out its a load bearing line of code YOU WILL DROP FRAMES IF THIS IS COMMENTED OUT IDK WHY BUT YOU WILL DONT DO IT
                        self.logger.info('Trigger type: %s', trigger.type) 
                        triggers[trigger_index] = trigger.timestamp
                        trigger_index += 1
        
        # acompanying tailing code from master
        if trigger_index > 0:
            target_us = triggers[trigger_index - 1] + self.offset_us + self.window_us
            deadline = time.time() + 5.0
            while self.camera.isRunning() and time.time() < deadline:
                event_batch = self.camera.getNextEventBatch()
                if event_batch is None or len(event_batch) == 0:
                    continue
                events = np.concatenate((events, event_batch.numpy()))
                if int(events['timestamp'][-1]) >= target_us:
                    break

        # Remove the initial zero from the triggers and events arrays
        events = events[1:]
        self.logger.info(f'Recording complete.\n {Font.BOLD}Triggers:{Font.ENDC} %s\n {Font.BOLD}Events:{Font.ENDC} %s', len(triggers), len(events))
        return (triggers, events)
    
    def skip_startup_leader_triggers(self, triggers: np.ndarray, leader_trigger_count: int) -> np.ndarray:
        """Drop the leading non-semantic triggers the startup leader emitted."""
        requested = int(leader_trigger_count or 0)
        skipped = min(max(0, requested), len(triggers))
        remaining = np.asarray(triggers)[skipped:]
        self.logger.info('skipped %s leader triggers, %s remain', skipped, len(remaining))
        return remaining

    def align_triggers_to_event_range(self, triggers: np.ndarray, events: np.ndarray) -> np.ndarray:
        """Drop triggers whose accumulation window falls outside the recorded events.

        Uses ON events only, since accumulate() integrates only those.
        """
        if len(triggers) == 0 or len(events) == 0 or self.window_us <= 0:
            return triggers

        window_starts = np.asarray(triggers, dtype=np.int64) + int(self.offset_us)
        window_ends = window_starts + int(self.window_us)

        lit = events[events['polarity'] != 0]
        if len(lit) == 0:
            return triggers
        ts = np.sort(lit['timestamp'].astype(np.int64))

        counts = (np.searchsorted(ts, window_ends, 'left')
                  - np.searchsorted(ts, window_starts, 'left'))
        threshold = max(1.0, self.signal_fraction * np.percentile(counts, 75))
        strong = np.flatnonzero(counts >= threshold)
        if len(strong) == 0:
            self.logger.warning('no trigger window reached the signal threshold (%.0f events)', threshold)
            return triggers

        first = int(strong[0])
        last = min(len(triggers) - 1, int(strong[-1]) + 1)
        aligned = np.asarray(triggers)[first:last + 1]
        self.logger.info('aligned to events, dropped %s before, %s after, %s remain (threshold %.0f events)',
                         first, len(triggers) - 1 - last, len(aligned), threshold)
        return aligned

    def _to_image(self, frame: np.ndarray) -> np.ndarray:
        magnitude = np.abs(np.asarray(frame, dtype=np.float32))
        maximum = float(self.normalize_scale_max)
        if maximum <= 0:
            return np.zeros(magnitude.shape, dtype=np.uint8)
        scaled = np.log1p(magnitude) * (255.0 / np.log1p(maximum))
        return np.rint(np.clip(scaled, 0, 255)).astype(np.uint8)

    def accumulate(self, triggers: np.ndarray, events: np.ndarray) -> np.ndarray:
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
        
        # Slice up data between timestamps and accumulate
        frames = np.zeros((len(triggers), self.ROI_HEIGHT, self.ROI_WIDTH))
        for idx in range(len(triggers)):
            # Clip to window size and offset
            event_slice = events[
                (events[:]['timestamp'] >= triggers[idx] + self.offset_us) &
                (events[:]['timestamp'] < triggers[idx] + self.offset_us + self.window_us) 
                # (events[:]['timestamp'] < triggers[idx + 1]) if idx + 1 < len(triggers) else False
            ]
            self.logger.debug('Accumulating frame %s with %s events', idx, len(event_slice))
            
            if len(event_slice) == 0:
                self.logger.warning('No events found for frame %s. Frame will be empty.', idx)
                self.logger.info('idx: %s, trigger ts - next trigger ts: %s', idx, triggers[idx+1] - triggers[idx] if idx + 1 < len(triggers) else 'N/A')
                continue
            
            # Accumulate the events into a frame
            for event in event_slice:
                x, y, polarity = event['x'], event['y'], event['polarity']
                frames[idx, y, x] += 1 if polarity else 0
                
        self.logger.info(f'Accumulation complete.\n `frames` shape: %s', frames.shape)
            
        return frames
    
    def save(self, frames: np.ndarray, folder: Path, save_as_png: Optional[bool] = False):
        """
        Saves accumulated event frames to a folder.

        Args:
            frames (np.ndarray): A numpy array of shape (len(triggers), ROI_HEIGHT, ROI_WIDTH) containing the accumulated frames.
            folder (str): Folder to save to.
            save_as_png (Optional[bool], optional): Whether or not to save the frames as PNG files. Defaults to False.
        """
        # Create the folder if it doesn't exist
        os.makedirs(folder, exist_ok=True)
        for idx, frame in enumerate(frames):
            if save_as_png:
                # Save the frames to a .png file
                Image.fromarray(self._to_image(frame), mode='L').save(f'{folder}/frame_{idx}.png', format='PNG')
            else:
                # Save the frames to a .npy file
                np.save(f'{folder}/frame_{idx}.npy', frame)
        
        self.logger.info('Saved %s frames to %s', len(frames), folder)
        
    def contact_sheet(
        self, 
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
        contact_sheet = Image.new('L', (self.ROI_WIDTH * grid_size[0], self.ROI_HEIGHT * grid_size[1]))
        
        for idx, frame in enumerate(frames):
            if idx >= grid_size[0] * grid_size[1]:
                break
            # Normalize and convert frame to image
            frame_img = Image.fromarray(self._to_image(frame), mode='L')
            x_offset = (idx % grid_size[0]) * self.ROI_WIDTH
            y_offset = (idx // grid_size[0]) * self.ROI_HEIGHT
            contact_sheet.paste(frame_img, (x_offset, y_offset))
        
        # Save the contact sheet
        contact_sheet.save(save_path, format='PNG')
        self.logger.info('Saved contact sheet to %s', save_path)


class CameraProphsee(CameraDAVIS):
    """
    Class to control Prophesee event cameras via OpenEB.
    """
    def __init__(self):
        self.logger = logging.getLogger('Camera')

        # Open camera & enable trigger input
        self.camera = MetavisionCamera.from_first_available()
        device = self.camera.get_device()
        trigger_in = device.get_i_trigger_in()
        if trigger_in is not None:
            trigger_in.enable(I_TriggerIn.Channel.MAIN)
            self.logger.info('Enabled Prophesee trigger input on Channel.MAIN')
        else:
            self.logger.warning('Prophesee device does not expose I_TriggerIn interface')

        self.WIDTH = self.camera.width()
        self.HEIGHT = self.camera.height()
        self.logger.info('Prophesee camera opened at %s x %s', self.WIDTH, self.HEIGHT)

        # ROI settings from config
        roi_cfg = CONFIG.get('Camera', {}).get('ROI', {})
        self.roi_start_x = int(roi_cfg.get('start_x', 0))
        self.roi_start_y = int(roi_cfg.get('start_y', 0))
        self.ROI_WIDTH = int(roi_cfg.get('width', self.WIDTH))
        self.ROI_HEIGHT = int(roi_cfg.get('height', self.HEIGHT))

        # Hardware ROI on sensor silicon (I_ROI)
        is_full_frame = (
            self.roi_start_x == 0 and
            self.roi_start_y == 0 and
            self.ROI_WIDTH == self.WIDTH and
            self.ROI_HEIGHT == self.HEIGHT
        )

        i_roi = device.get_i_roi() if device is not None else None
        if i_roi is not None:
            if is_full_frame:
                try:
                    i_roi.enable(False)
                    self.logger.info("Prophesee hardware ROI disabled (full sensor %dx%d)", self.WIDTH, self.HEIGHT)
                except Exception as exc:
                    self.logger.debug("Could not disable hardware ROI: %s", exc)
            else:
                try:
                    if hasattr(I_ROI, "Mode") and hasattr(I_ROI.Mode, "ROI"):
                        i_roi.set_mode(I_ROI.Mode.ROI)
                    if hasattr(I_ROI, "Window"):
                        window = I_ROI.Window(self.roi_start_x, self.roi_start_y, self.ROI_WIDTH, self.ROI_HEIGHT)
                        i_roi.set_window(window)
                    else:
                        i_roi.set_window(self.roi_start_x, self.roi_start_y, self.ROI_WIDTH, self.ROI_HEIGHT)
                    i_roi.enable(True)
                    self.logger.info(
                        "Enabled Prophesee hardware ROI on sensor silicon: origin=(%d, %d), size=%dx%d",
                        self.roi_start_x, self.roi_start_y, self.ROI_WIDTH, self.ROI_HEIGHT,
                    )
                except Exception as exc:
                    self.logger.warning("Failed to configure hardware I_ROI: %s", exc)
        else:
            if not is_full_frame:
                self.logger.warning("Prophesee device does not expose I_ROI interface; software cropping will apply")

        # No background noise filtering
        self.filter = None

        # Slicer
        slice_us = int(CONFIG.get('Camera', {}).get('slice_duration_us', 10_000))
        self.slicer = CameraStreamSlicer(self.camera.move(), slice_condition=SliceCondition.make_n_us(slice_us))
        self._slicer_iter = iter(self.slicer)

        # Accumulation settings
        self.window_us = CONFIG.get('Camera', {}).get('Accumulation', {}).get('window_us', 16000)
        self.offset_us = CONFIG.get('Camera', {}).get('Accumulation', {}).get('start_time_offset_us', 0)
        self.polarity_mode = str(CONFIG.get('Camera', {}).get('Accumulation', {}).get('polarity_mode', 'positive')).lower()
        self.normalize_scale_max = CONFIG.get('Camera', {}).get('normalize_scale_max', 255)
        self.signal_fraction = CONFIG.get('Camera', {}).get('signal_fraction', 0.1)

    def flush(self, flush_count: int = 32):
        """Flush stale slices from the stream buffer."""
        for _ in range(min(flush_count, 5)):
            try:
                next(self._slicer_iter)
            except StopIteration:
                break

    def record(self, trigger_count: int, on_complete: Any = None) -> tuple:
        """Record event data for a set amount of triggers.

        Args:
            trigger_count: Target number of triggers to record.
            on_complete: Optional callback invoked immediately when all triggers
                have been recorded, before large event concatenation.
        """
        import gc
        events, triggers = [], []
        self.logger.info('Recording %s triggers from Prophesee camera...', trigger_count)

        gc_was_enabled = gc.isenabled()
        if gc_was_enabled:
            gc.disable()
        try:
            for s in self._slicer_iter:
                events.append(s.events.copy())
                if len(s.triggers) > 0:
                    matching = s.triggers["t"][s.triggers["p"] == 1]
                    triggers.extend(matching.tolist())
                if len(triggers) >= trigger_count:
                    break
        finally:
            if gc_was_enabled:
                gc.enable()

        triggers_arr = np.array(triggers[:trigger_count], dtype=np.int64)

        if callable(on_complete):
            try:
                on_complete()
            except Exception as e:
                self.logger.warning("on_complete callback failed: %s", e)

        concatenated = np.concatenate(events) if len(events) > 0 else np.empty(0)
        self.logger.info('Recording complete. Triggers: %s, Events: %s', len(triggers_arr), len(concatenated))
        return (triggers_arr, concatenated)

    def align_triggers_to_event_range(self, triggers: np.ndarray, events: np.ndarray) -> np.ndarray:
        """Drop triggers whose accumulation window falls outside the recorded events."""
        if len(triggers) == 0 or len(events) == 0:
            return triggers

        window_starts = np.asarray(triggers, dtype=np.int64) + int(self.offset_us)
        window_ends = window_starts + int(self.window_us)

        lit = events[events['p'] != 0]
        if len(lit) == 0:
            return triggers
        ts = np.sort(lit['t'].astype(np.int64))

        counts = np.searchsorted(ts, window_ends, 'left') - np.searchsorted(ts, window_starts, 'left')
        threshold = max(1.0, self.signal_fraction * np.percentile(counts, 75))
        strong = np.flatnonzero(counts >= threshold)
        if len(strong) == 0:
            return triggers

        first, last = int(strong[0]), int(strong[-1])
        return np.asarray(triggers)[first:last + 1]

    def accumulate(self, triggers: np.ndarray, events: np.ndarray) -> np.ndarray:
        """Accumulate recorded event stream into frames."""
        self.logger.info('Accumulating %s events into %s frames...', len(events), len(triggers))
        frames = np.zeros((len(triggers), self.ROI_HEIGHT, self.ROI_WIDTH))
        if len(triggers) == 0 or len(events) == 0:
            return frames

        ev_t, ev_x, ev_y, ev_p = events['t'], events['x'], events['y'], events['p']
        starts = np.asarray(triggers, dtype=np.int64) + int(self.offset_us)
        ends = starts + int(self.window_us)

        idx_starts = np.searchsorted(ev_t, starts, 'left')
        idx_ends = np.searchsorted(ev_t, ends, 'left')

        is_signed = self.polarity_mode == 'signed'
        total_pixels = self.ROI_HEIGHT * self.ROI_WIDTH

        for idx in range(len(triggers)):
            s_i, e_i = idx_starts[idx], idx_ends[idx]
            if s_i >= e_i:
                continue

            sl_x = ev_x[s_i:e_i]
            sl_y = ev_y[s_i:e_i]
            sl_p = ev_p[s_i:e_i]

            loc_x = sl_x - self.roi_start_x
            loc_y = sl_y - self.roi_start_y

            valid = (loc_x >= 0) & (loc_x < self.ROI_WIDTH) & (loc_y >= 0) & (loc_y < self.ROI_HEIGHT)
            if not np.any(valid):
                continue

            flat_coords = loc_y[valid].astype(np.int64) * self.ROI_WIDTH + loc_x[valid].astype(np.int64)
            if is_signed:
                weights = np.where(sl_p[valid] != 0, 1.0, -1.0)
                frame = np.bincount(flat_coords, weights=weights, minlength=total_pixels).reshape(
                    (self.ROI_HEIGHT, self.ROI_WIDTH)
                )
            else:
                on = sl_p[valid] != 0
                frame = np.bincount(flat_coords[on], minlength=total_pixels).reshape(
                    (self.ROI_HEIGHT, self.ROI_WIDTH)
                )
            frames[idx] = frame

        self.logger.info(f'Accumulation complete.\n `frames` shape: %s', frames.shape)
        return frames
