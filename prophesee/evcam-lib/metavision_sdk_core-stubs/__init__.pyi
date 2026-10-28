from __future__ import annotations
import collections.abc
import metavision_sdk_base
import numpy
import numpy.dtypes
import numpy.typing
import typing
__all__: list[str] = ['AdaptiveRateEventsSplitterAlgorithm', 'Auxiliary', 'Background', 'BaseFrameGenerationAlgorithm', 'ColorPalette', 'ColorType', 'ContrastMapGenerationAlgorithm', 'CoolWarm', 'Dark', 'EventBbox', 'EventBboxBuffer', 'EventPreprocessor', 'EventRescalerAlgorithm', 'EventTrackedBox', 'EventTrackedBoxBuffer', 'EventsIntegrationAlgorithm', 'FlipXAlgorithm', 'FlipYAlgorithm', 'Gray', 'Light', 'MostRecentTimestampBuffer', 'Negative', 'OnDemandFrameGenerationAlgorithm', 'PeriodicFrameGenerationAlgorithm', 'PolarityFilterAlgorithm', 'PolarityInverterAlgorithm', 'Positive', 'RawEventFrameConverter', 'RoiFilterAlgorithm', 'RoiMaskAlgorithm', 'RollingEventBufferConfig', 'RollingEventBufferMode', 'RollingEventCDBuffer', 'RotateEventsAlgorithm', 'SharedCdEventsBufferProducer', 'StreamLoggerAlgorithm', 'TransposeEventsAlgorithm', 'getColor', 'hsv2rgb', 'rgb2hsv']
class EventBboxBuffer:
    def __buffer__(self, flags):
        """
        Return a buffer object that exposes the underlying memory of the object.
        """
    def __init__(self, size: typing.SupportsInt | typing.SupportsIndex = 0) -> None:
        """
        Constructor
        """
    def __release_buffer__(self, buffer):
        """
        Release the buffer object that exposes the underlying memory of the object.
        """
    def _buffer_info(self) -> metavision_sdk_base._BufferInfo:
        ...
    def numpy(self, copy: bool = False) -> numpy.typing.NDArray[...]:
        """
           :copy: if True, allocates new memory and returns a copy of the events. If False, use the same memory
        """
    def resize(self, size: typing.SupportsInt | typing.SupportsIndex) -> None:
        """
        resizes the buffer to the specified size
        
           :size: the new size of the buffer
        """
class EventTrackedBoxBuffer:
    def __buffer__(self, flags):
        """
        Return a buffer object that exposes the underlying memory of the object.
        """
    def __init__(self, size: typing.SupportsInt | typing.SupportsIndex = 0) -> None:
        """
        Constructor
        """
    def __release_buffer__(self, buffer):
        """
        Release the buffer object that exposes the underlying memory of the object.
        """
    def _buffer_info(self) -> metavision_sdk_base._BufferInfo:
        ...
    def numpy(self, copy: bool = False) -> numpy.typing.NDArray[...]:
        """
           :copy: if True, allocates new memory and returns a copy of the events. If False, use the same memory
        """
    def resize(self, size: typing.SupportsInt | typing.SupportsIndex) -> None:
        """
        resizes the buffer to the specified size
        
           :size: the new size of the buffer
        """
class ColorPalette:
    """
    Members:
    
      Light
    
      Dark
    
      CoolWarm
    
      Gray
    """
    CoolWarm: typing.ClassVar[ColorPalette]
    Dark: typing.ClassVar[ColorPalette]
    Gray: typing.ClassVar[ColorPalette]
    Light: typing.ClassVar[ColorPalette]
    __members__: typing.ClassVar[dict[str, ColorPalette]]
    @typing.overload
    def __eq__(self, other: ColorPalette) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: ColorPalette) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class ColorType:
    """
    Members:
    
      Background
    
      Positive
    
      Negative
    
      Auxiliary
    """
    Auxiliary: typing.ClassVar[ColorType]
    Background: typing.ClassVar[ColorType]
    Negative: typing.ClassVar[ColorType]
    Positive: typing.ClassVar[ColorType]
    __members__: typing.ClassVar[dict[str, ColorType]]
    @typing.overload
    def __eq__(self, other: ColorType) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: ColorType) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class MostRecentTimestampBuffer:
    """Class representing a buffer of the most recent timestamps observed at each pixel of the camera."""
    def __buffer__(self, flags):
        """
        Return a buffer object that exposes the underlying memory of the object.
        """
    def __init__(self, rows: typing.SupportsInt | typing.SupportsIndex, cols: typing.SupportsInt | typing.SupportsIndex, channels: typing.SupportsInt | typing.SupportsIndex = 1) -> None:
        ...
    def __release_buffer__(self, buffer):
        """
        Release the buffer object that exposes the underlying memory of the object.
        """
    def _buffer_info(self) -> metavision_sdk_base._BufferInfo:
        ...
    def generate_img_time_surface(self, last_ts: typing.SupportsInt | typing.SupportsIndex, delta_t: typing.SupportsInt | typing.SupportsIndex, out: numpy.ndarray) -> None:
        """Generates a CV_8UC1 image of the time surface for the 2 channels."""
    def generate_img_time_surface_collapsing_channels(self, last_ts: typing.SupportsInt | typing.SupportsIndex, delta_t: typing.SupportsInt | typing.SupportsIndex, out: numpy.ndarray) -> None:
        """Generates a CV_8UC1 image of the time surface, merging the 2 channels."""
    def max_across_channels_at(self, y: typing.SupportsInt | typing.SupportsIndex, x: typing.SupportsInt | typing.SupportsIndex) -> int:
        """Retrieves the maximum timestamp across channels at the specified pixel."""
    def numpy(self, copy: bool = False) -> numpy.typing.NDArray[numpy.int64]:
        """
        Converts to a numpy array
        """
    def set_to(self, ts: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Sets all elements of the timestamp buffer to a constant."""
    @property
    def channels(self) -> int:
        """Gets the number of channels of the buffer."""
    @property
    def cols(self) -> int:
        """Gets the number of columns of the buffer."""
    @property
    def rows(self) -> int:
        """Gets the number of rows of the buffer."""
class AdaptiveRateEventsSplitterAlgorithm:
    """Class used to split a stream of events into slices of variable duration and variable number of events."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, height: typing.SupportsInt | typing.SupportsIndex, width: typing.SupportsInt | typing.SupportsIndex, thr_var_per_event: typing.SupportsFloat | typing.SupportsIndex = 0.0005, downsampling_factor: typing.SupportsInt | typing.SupportsIndex = 2) -> None:
        ...
    @typing.overload
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> bool:
        """
        Takes a chunk of events (numpy array of EventCD) and updates the internal state of the EventsSplitter. Returns True if the frame is ready, False otherwise.
        """
    @typing.overload
    def process_events(self, events_buf: metavision_sdk_base.EventCDBuffer) -> bool:
        """
        Takes a chunk of events (EventCDBuffer) and updates the internal state of the EventsSplitter. Returns True if the frame is ready, False otherwise.
        """
    def retrieve_events(self, events_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        Retrieves the events (EventCDBuffer) and reinitializes the state of the EventsSplitter.
        """
class BaseFrameGenerationAlgorithm:
    @staticmethod
    def bg_color_default() -> tuple:
        """Returns default Prophesee dark palette background color."""
    @staticmethod
    @typing.overload
    def generate_frame(events: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], frame: numpy.ndarray, accumulation_time_us: typing.SupportsInt | typing.SupportsIndex = 0, palette: ColorPalette = ...) -> None:
        """
        Stand-alone (static) method to generate a frame from events
        
           All events in the interval ]t - dt, t] are used where t the timestamp of the last event in the buffer, and dt is accumulation_time_us. If accumulation_time_us is kept to 0, all input events are used.
           If there is no events, a frame filled with the background color will be generated
        
           :events: Numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
           :frame: Pre-allocated frame that will be filled with CD events. It must have the same geometry as the input event source, and the color corresponding to the given palette (3 channels by default)
           :accumulation_time_us: Time range of events to update the frame with (in us). 0 to use all events.
           :palette: The Prophesee's color palette to use
        """
    @staticmethod
    @typing.overload
    def generate_frame(events: typing.Any, frame: numpy.ndarray, accumulation_time_us: typing.SupportsInt | typing.SupportsIndex = 0, palette: ColorPalette = ...) -> None:
        """
        Stand-alone (static) method to generate a frame from events
        
           All events in the interval ]t - dt, t] are used where t the timestamp of the last event in the buffer, and dt is accumulation_time_us. If accumulation_time_us is kept to 0, all input events are used.
           If there is no events, a frame filled with the background color will be generated
        
           :events: Numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
           :frame: Pre-allocated frame that will be filled with CD events. It must have the same geometry as the input event source, and the color corresponding to the given palette (3 channels by default)
           :accumulation_time_us: Time range of events to update the frame with (in us). 0 to use all events.
           :palette: The Prophesee's color palette to use
        """
    @staticmethod
    def off_color_default() -> tuple:
        """Returns default Prophesee dark palette negative event color."""
    @staticmethod
    def on_color_default() -> tuple:
        """Returns default Prophesee dark palette positive event color."""
    def get_dimension(self) -> tuple[int, int, int]:
        """
        Gets the frame's dimension, a tuple (height, width, channels)
        """
    def set_color_palette(self, palette: ColorPalette) -> None:
        """Sets the color used to generate the frame."""
    def set_colors(self, background_color: collections.abc.Sequence[typing.SupportsInt | typing.SupportsIndex], on_color: collections.abc.Sequence[typing.SupportsInt | typing.SupportsIndex], off_color: collections.abc.Sequence[typing.SupportsInt | typing.SupportsIndex], colored: bool = True) -> None:
        """Sets the color used to generate the frame."""
class ContrastMapGenerationAlgorithm:
    def __init__(self, width: typing.SupportsInt | typing.SupportsIndex, height: typing.SupportsInt | typing.SupportsIndex, contrast_on: typing.SupportsFloat | typing.SupportsIndex = 1.2000000476837158, contrast_off: typing.SupportsFloat | typing.SupportsIndex = -1.0) -> None:
        ...
    @typing.overload
    def generate(self, frame: numpy.ndarray) -> None:
        """Generates the contrast map and resets the internal state."""
    @typing.overload
    def generate(self, frame: numpy.ndarray, tonemapping_factor: typing.SupportsFloat | typing.SupportsIndex, tonemapping_bias: typing.SupportsFloat | typing.SupportsIndex) -> None:
        """Generates the tonemapped contrast map and resets the internal state."""
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Processes a buffer of events for later frame generation
        
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
        """
    def reset(self) -> None:
        """Resets the internal state."""
class EventPreprocessor:
    """Processes events to update data from a tensor."""
    @staticmethod
    def create_DiffProcessor(input_event_width: typing.SupportsInt | typing.SupportsIndex, input_event_height: typing.SupportsInt | typing.SupportsIndex, max_incr_per_pixel: typing.SupportsFloat | typing.SupportsIndex = 5, clip_value_after_normalization: typing.SupportsFloat | typing.SupportsIndex = 1.0, scale_width: typing.SupportsFloat | typing.SupportsIndex = 1.0, scale_height: typing.SupportsFloat | typing.SupportsIndex = 1.0) -> EventPreprocessor:
        """Constructor."""
    @staticmethod
    def create_EventCubeProcessor(delta_t: typing.SupportsInt | typing.SupportsIndex, input_event_width: typing.SupportsInt | typing.SupportsIndex, input_event_height: typing.SupportsInt | typing.SupportsIndex, num_utbins: typing.SupportsInt | typing.SupportsIndex, split_polarity: bool, max_incr_per_pixel: typing.SupportsFloat | typing.SupportsIndex = 63.75, clip_value_after_normalization: typing.SupportsFloat | typing.SupportsIndex = 1.0, scale_width: typing.SupportsFloat | typing.SupportsIndex = 1.0, scale_height: typing.SupportsFloat | typing.SupportsIndex = 1.0) -> EventPreprocessor:
        """Constructor."""
    @staticmethod
    def create_HardwareDiffProcessor(input_event_width: typing.SupportsInt | typing.SupportsIndex, input_event_height: typing.SupportsInt | typing.SupportsIndex, min_val: typing.SupportsInt | typing.SupportsIndex, max_val: typing.SupportsInt | typing.SupportsIndex, allow_rollover: bool = True) -> EventPreprocessor:
        """Constructor."""
    @staticmethod
    def create_HardwareHistoProcessor(input_event_width: typing.SupportsInt | typing.SupportsIndex, input_event_height: typing.SupportsInt | typing.SupportsIndex, neg_saturation: typing.SupportsInt | typing.SupportsIndex = 255, pos_saturation: typing.SupportsInt | typing.SupportsIndex = 255) -> EventPreprocessor:
        """Constructor."""
    @staticmethod
    def create_HistoProcessor(input_event_width: typing.SupportsInt | typing.SupportsIndex, input_event_height: typing.SupportsInt | typing.SupportsIndex, max_incr_per_pixel: typing.SupportsFloat | typing.SupportsIndex = 5, clip_value_after_normalization: typing.SupportsFloat | typing.SupportsIndex = 1.0, use_CHW: bool = True, scale_width: typing.SupportsFloat | typing.SupportsIndex = 1.0, scale_height: typing.SupportsFloat | typing.SupportsIndex = 1.0) -> EventPreprocessor:
        """Constructor."""
    @staticmethod
    def create_TimeSurfaceProcessor(input_event_width: typing.SupportsInt | typing.SupportsIndex, input_event_height: typing.SupportsInt | typing.SupportsIndex, split_polarity: bool = True) -> EventPreprocessor:
        """
                                        Creates a TimeSurfaceProcessor instance.
        
                                            :input_event_width: Width of the input event stream.
                                            :input_event_height: Height of the input event stream.
                                            :split_polarity: (optional) If True, polarities will be managed separately in the
                                                             TimeSurface. Else, a single channel will be used for both
                                                             polarities.
        """
    def get_frame_channels(self) -> int:
        """
        Returns the number of channels of the output frame.
        """
    def get_frame_height(self) -> int:
        """
        Returns the height of the output frame.
        """
    def get_frame_shape(self) -> list[int]:
        """
        Returns the frame shape.
        """
    def get_frame_size(self) -> int:
        """
        Returns the number of values in the output frame.
        """
    def get_frame_width(self) -> int:
        """
        Returns the width of the output frame.
        """
    def init_output_tensor(self) -> numpy.ndarray:
        ...
    def is_CHW(self) -> bool:
        """
        Returns true if the output tensor shape has CHW layout.
        """
    def process_events(self, cur_frame_start_ts: typing.SupportsInt | typing.SupportsIndex, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], frame_tensor_np: numpy.ndarray) -> None:
        """
        Takes a chunk of events (numpy array of EventCD) and updates the frame_tensor (numpy array of float)
        """
class EventRescalerAlgorithm:
    """Base class to operate a rescaling of events locations in both horizontal and vertical directions."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, scale_width: typing.SupportsFloat | typing.SupportsIndex, scale_height: typing.SupportsFloat | typing.SupportsIndex) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input/output.
        This method should only be used when the number of output events is the same as the number of input events
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't') used as input/output. Its content will be overwritten
        """
class EventsIntegrationAlgorithm:
    def __init__(self, width: typing.SupportsInt | typing.SupportsIndex, height: typing.SupportsInt | typing.SupportsIndex, decay_time: typing.SupportsInt | typing.SupportsIndex = 1000000, contrast_on: typing.SupportsFloat | typing.SupportsIndex = 1.2000000476837158, contrast_off: typing.SupportsFloat | typing.SupportsIndex = -1.0, tonemapping_max_ev_count: typing.SupportsInt | typing.SupportsIndex = 5, gaussian_blur_kernel_radius: typing.SupportsInt | typing.SupportsIndex = 1, diffusion_weight: typing.SupportsFloat | typing.SupportsIndex = 0.0) -> None:
        ...
    def generate(self, frame: numpy.ndarray) -> None:
        """Generates the grayscale frame at the timestamp of the last received event."""
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Processes a buffer of events for later frame generation
        
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
        """
    def reset(self) -> None:
        """Resets the internal state."""
class FlipXAlgorithm:
    """Class that allows to mirror the X axis of an event stream."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, width_minus_one: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input/output.
        This method should only be used when the number of output events is the same as the number of input events
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't') used as input/output. Its content will be overwritten
        """
    @property
    def width_minus_one(self) -> int:
        ...
    @width_minus_one.setter
    def width_minus_one(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class FlipYAlgorithm:
    """Class that allows to mirror the Y axis of an event stream."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, height_minus_one: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input/output.
        This method should only be used when the number of output events is the same as the number of input events
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't') used as input/output. Its content will be overwritten
        """
    @property
    def height_minus_one(self) -> int:
        ...
    @height_minus_one.setter
    def height_minus_one(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class OnDemandFrameGenerationAlgorithm(BaseFrameGenerationAlgorithm):
    def __init__(self, width: typing.SupportsInt | typing.SupportsIndex, height: typing.SupportsInt | typing.SupportsIndex, accumulation_time_us: typing.SupportsInt | typing.SupportsIndex = 10000, palette: ColorPalette = ...) -> None:
        ...
    def generate(self, ts: typing.SupportsInt | typing.SupportsIndex, frame: numpy.ndarray) -> None:
        """Generates a frame."""
    def get_accumulation_time_us(self) -> int:
        """Returns the current accumulation time (in us)."""
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Processes a buffer of events for later frame generation
        
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
        """
    def set_accumulation_time_us(self, accumulation_time_us: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Sets the accumulation time (in us) to use to generate a frame."""
class PeriodicFrameGenerationAlgorithm(BaseFrameGenerationAlgorithm):
    def __init__(self, sensor_width: typing.SupportsInt | typing.SupportsIndex, sensor_height: typing.SupportsInt | typing.SupportsIndex, accumulation_time_us: typing.SupportsInt | typing.SupportsIndex = 10000, fps: typing.SupportsFloat | typing.SupportsIndex = 0.0, palette: ColorPalette = ...) -> None:
        """
        Inherits BaseFrameGenerationAlgorithm. Algorithm that generates frames from events at a fixed rate (fps). The reference clock used is the one of the input events
        
        Args:
            sensor_width (int): Sensor's width (in pixels)
            sensor_height (int): Sensor's height (in pixels)
            accumulation_time_us (timestamp): Accumulation time (in us) (@ref set_accumulation_time_us)
            fps (float): The fps at which to generate the frames. The time reference used is the one from the input events (@ref set_fps) 
            palette (ColorPalette): The Prophesee's color palette to use (@ref set_color_palette)
        @throw std::invalid_argument If the input fps is not positive or if the input accumulation time is not strictly positive
        """
    def force_generate(self) -> None:
        """Forces the generation of a frame for the current period with the input events that have been processed."""
    def get_accumulation_time_us(self) -> int:
        """Returns the current accumulation time (in us)."""
    def get_fps(self) -> float:
        """Returns the current fps at which frames are generated."""
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Processes a buffer of events for later frame generation
        
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
        """
    def reset(self) -> None:
        """Resets the internal states."""
    def set_accumulation_time_us(self, accumulation_time_us: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Sets the accumulation time (in us) to use to generate a frame."""
    def set_fps(self, fps: typing.SupportsFloat | typing.SupportsIndex) -> None:
        """Sets the fps at which to generate frames and thus the frequency of the asynchronous calls."""
    def set_output_callback(self, arg0: typing.Any) -> None:
        """
        Sets a callback to retrieve the frame
        """
    def skip_frames_up_to(self, ts: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Skips the generation of frames up to the timestamp ts."""
class PolarityFilterAlgorithm:
    """Class filter that only propagates events of a certain polarity."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, polarity: typing.SupportsInt | typing.SupportsIndex = 0) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input/output.
        This should only be used when the number of output events is the same as the number of input events
           :events_buf: Buffer of events used as input/output. Its content will be overwritten. It can be converted to a numpy structured array using .numpy()
        """
    @property
    def polarity(self) -> int:
        ...
    @polarity.setter
    def polarity(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class PolarityInverterAlgorithm:
    """Class that implements a Polarity Inverter filter."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input/output.
        This method should only be used when the number of output events is the same as the number of input events
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't') used as input/output. Its content will be overwritten
        """
class RawEventFrameConverter:
    ...
    def __init__(self, height: typing.SupportsInt | typing.SupportsIndex, width: typing.SupportsInt | typing.SupportsIndex, use_CHW: bool = False) -> None:
        """
        Creates a RawEventFrameConverter
        """
    def convert_diff(self, arg0: metavision_sdk_base.RawEventFrameDiff) -> numpy.typing.NDArray[numpy.int8]:
        """
        Converts a RawEventFrameDiff into a proper diff frame
        """
    def convert_histo(self, arg0: metavision_sdk_base.RawEventFrameHisto) -> numpy.typing.NDArray[numpy.uint8]:
        """
        Converts a RawEventFrameHisto into a proper histo frame
        """
    def set_CHW(self) -> None:
        """
        Set histo output format to CHW
        """
    def set_HWC(self) -> None:
        """
        Set histo output format to HWC
        """
class RoiFilterAlgorithm:
    """Class that only propagates events which are contained in a certain Region of Interest (ROI) defined by the coordinates of the upper left corner and the lower right corner."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, x0: typing.SupportsInt | typing.SupportsIndex, y0: typing.SupportsInt | typing.SupportsIndex, x1: typing.SupportsInt | typing.SupportsIndex, y1: typing.SupportsInt | typing.SupportsIndex, output_relative_coordinates: bool = False) -> None:
        ...
    def is_resetting(self) -> bool:
        """Returns true if the algorithm returns events expressed in coordinates relative to the ROI."""
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input/output.
        This should only be used when the number of output events is the same as the number of input events
           :events_buf: Buffer of events used as input/output. Its content will be overwritten. It can be converted to a numpy structured array using .numpy()
        """
    @property
    def x0(self) -> int:
        """Returns the x coordinate of the upper left corner of the ROI window."""
    @x0.setter
    def x0(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def x1(self) -> int:
        """Returns the x coordinate of the lower right corner of the ROI window."""
    @x1.setter
    def x1(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def y0(self) -> int:
        """Returns the y coordinate of the upper left corner of the ROI window."""
    @y0.setter
    def y0(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def y1(self) -> int:
        """Returns the y coordinate of the lower right corner of the ROI window."""
    @y1.setter
    def y1(self, arg1: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class RoiMaskAlgorithm:
    """Class that only propagates events which are contained in a certain region of interest."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, pixel_mask: typing.Annotated[numpy.typing.ArrayLike, numpy.float64]) -> None:
        ...
    def enable_rectangle(self, x0: typing.SupportsInt | typing.SupportsIndex, y0: typing.SupportsInt | typing.SupportsIndex, x1: typing.SupportsInt | typing.SupportsIndex, y1: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Enables a rectangular region defined by the upper left corner and the bottom right corner that propagates any event inside them."""
    def max_height(self) -> int:
        """Returns the maximum number of pixels (height) of the mask."""
    def max_width(self) -> int:
        """Returns the maximum number of pixels (width) of the mask."""
    def pixel_mask(self) -> numpy.typing.NDArray[numpy.float64]:
        """Returns the pixel mask of the filter."""
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    def process_events_(self, events_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input/output.
        This should only be used when the number of output events is the same as the number of input events
           :events_buf: Buffer of events used as input/output. Its content will be overwritten. It can be converted to a numpy structured array using .numpy()
        """
    def set_pixel_mask(self, mask: typing.Annotated[numpy.typing.ArrayLike, numpy.float64]) -> None:
        """Sets the pixel mask of the filter."""
class RotateEventsAlgorithm:
    """class that allows to rotate an event stream."""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self, width_minus_one: typing.SupportsInt | typing.SupportsIndex, height_minus_one: typing.SupportsInt | typing.SupportsIndex, rotation: typing.SupportsFloat | typing.SupportsIndex) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events_(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input/output.
        This method should only be used when the number of output events is the same as the number of input events
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't') used as input/output. Its content will be overwritten
        """
    @typing.overload
    def process_events_(self, events_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input/output.
        This should only be used when the number of output events is the same as the number of input events
           :events_buf: Buffer of events used as input/output. Its content will be overwritten. It can be converted to a numpy structured array using .numpy()
        """
    def set_rotation(self, new_angle: typing.SupportsFloat | typing.SupportsIndex) -> None:
        """Sets the new rotation angle."""
    @property
    def height_minus_one(self) -> int:
        ...
    @height_minus_one.setter
    def height_minus_one(self) -> int:
        ...
    @property
    def width_minus_one(self) -> int:
        ...
    @width_minus_one.setter
    def width_minus_one(self) -> int:
        ...
class SharedCdEventsBufferProducer:
    """
    This class splits incoming events into buffers either by number of events or by time slice (in us)
    
    Incoming events are put in buffer contained in a pool of shared vectors until the buffer is completeThen a python callback specified by the user is called on the buffer of events.
    """
    def __init__(self, callback: typing.Any, event_count: typing.SupportsInt | typing.SupportsIndex = 0, time_slice_us: typing.SupportsInt | typing.SupportsIndex = 10000, buffers_pool_size: typing.SupportsInt | typing.SupportsIndex = 64, buffers_preallocation_size: typing.SupportsInt | typing.SupportsIndex = 0) -> None:
        """
        Args:
            callback (function): python callback taking as input an int coding the last timestamp of the buffer
                and a numpy buffer of EventCD.
            event_count (int): number of events in each buffer
            time_slice_us (int): duration of the buffer in us.
            buffers_pool_size (int): Number of shared pointers available in the pool at start. They will be 
                 increased if necessary automatically. Can be left as is in most cases.
            buffers_preallocation_size (int): initialization size of vectors in the memory pool. Here again,
                this can be left alone in most uses.
        """
    def flush(self) -> None:
        """
        Flushes the last buffers when the file is done, producing a last incomplete buffer.
        """
    def get_process_events_callback(self) -> collections.abc.Callable[[metavision_sdk_base._EventCD_decode, metavision_sdk_base._EventCD_decode], None]:
        """
        Returns a callback to be passed to the event_cd decoder from Metavision HAL.
        """
    def get_processing_n_events(self) -> int:
        ...
    def get_processing_n_us(self) -> int:
        ...
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Processes a buffer of events for later frame generation
        
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory
        """
    def reset(self) -> None:
        """
        Resets the buffer.
        """
    def set_processing_mixed(self, delta_n_events: typing.SupportsInt | typing.SupportsIndex, delta_ts: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def set_processing_n_events(self, delta_n_events: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def set_processing_n_us(self, delta_ts: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class StreamLoggerAlgorithm:
    ...
    def __init__(self, filename: str, width: typing.SupportsInt | typing.SupportsIndex, height: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def change_destination(self, filename: typing.Any, reset_ts: bool = True) -> None:
        ...
    def close(self) -> None:
        ...
    def enable(self, state: bool, reset_ts: bool = True, split_time_seconds: typing.SupportsInt | typing.SupportsIndex = -1) -> None:
        ...
    def get_native_process_cd_events_callback(self) -> collections.abc.Callable[[metavision_sdk_base._EventCD_decode, metavision_sdk_base._EventCD_decode], None]:
        """
        Returns a callback to be passed to the event_cd decoder from Metavision HAL.
        """
    def get_native_process_ext_trigger_events_callback(self) -> collections.abc.Callable[[metavision_sdk_base._EventExtTrigger_decode, metavision_sdk_base._EventExtTrigger_decode], None]:
        """
        Returns a callback to be passed to the event_ext_trigger decoder from Metavision HAL.
        """
    def get_split_time_seconds(self) -> int:
        ...
    def is_enable(self) -> bool:
        ...
    def process_events(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], ts: typing.SupportsInt | typing.SupportsIndex) -> None:
        """
        Processes a buffer of events for later frame generation
        
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory   :ts: array of events' timestamp
        """
class TransposeEventsAlgorithm:
    """Class that switches X and Y coordinates of an event stream. This filter changes the dimensions of the corresponding frame (width and height are switched)"""
    @staticmethod
    def get_empty_output_buffer() -> metavision_sdk_base.EventCDBuffer:
        """
        This function returns an empty buffer of events of the correct type, which can later on be used as output_buf when calling `process_events()`
        """
    def __init__(self) -> None:
        ...
    @typing.overload
    def process_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode], output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input and writes the results into the specified output event buffer
           :input_np: input chunk of events (numpy structured array whose fields are ('x', 'y', 'p', 't'). Note that this order is mandatory)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events(self, input_buf: metavision_sdk_base.EventCDBuffer, output_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input and writes the results into a distinct output event buffer
           :input_buf: input chunk of events (event buffer)
           :output_buf: output buffer of events. It can be converted to a numpy structured array using .numpy()
        """
    @typing.overload
    def process_events_(self, events_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes a numpy array as input/output.
        This method should only be used when the number of output events is the same as the number of input events
           :events_np: numpy structured array of events whose fields are ('x', 'y', 'p', 't') used as input/output. Its content will be overwritten
        """
    @typing.overload
    def process_events_(self, events_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This method is used to apply the current algorithm on a chunk of events. It takes an event buffer as input/output.
        This should only be used when the number of output events is the same as the number of input events
           :events_buf: Buffer of events used as input/output. Its content will be overwritten. It can be converted to a numpy structured array using .numpy()
        """
class RollingEventBufferMode:
    """
    Members:
    
      N_US
    
      N_EVENTS
    """
    N_EVENTS: typing.ClassVar[RollingEventBufferMode]
    N_US: typing.ClassVar[RollingEventBufferMode]
    __members__: typing.ClassVar[dict[str, RollingEventBufferMode]]
    @typing.overload
    def __eq__(self, other: RollingEventBufferMode) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    @typing.overload
    def __ne__(self, other: RollingEventBufferMode) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class RollingEventBufferConfig:
    mode: RollingEventBufferMode
    @staticmethod
    def make_n_events(*args, **kwargs) -> RollingEventBufferConfig:
        """Creates a RollingEventBufferConfig for the N_EVENTS mode."""
    @staticmethod
    def make_n_us(*args, **kwargs) -> RollingEventBufferConfig:
        """Creates a RollingEventBufferConfig for the N_US mode."""
    def __init__(self) -> None:
        ...
    @property
    def delta_n_events(self) -> int:
        ...
    @delta_n_events.setter
    def delta_n_events(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def delta_ts(self) -> int:
        ...
    @delta_ts.setter
    def delta_ts(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class RollingEventCDBuffer:
    def __init__(self, arg0: RollingEventBufferConfig) -> None:
        ...
    def __iter__(self) -> collections.abc.Iterator[metavision_sdk_base._EventCD_decode]:
        ...
    def capacity(self) -> int:
        """Returns the maximum capacity of the buffer."""
    def clear(self) -> None:
        """Clears the buffer, removing all stored events."""
    def empty(self) -> bool:
        """Checks if the buffer is empty."""
    @typing.overload
    def insert_events(self, input_np: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        This function inserts events from a numpy array into the rolling buffer based on the current mode (N_US or N_EVENTS)
            :input_np: input chunk of events
        """
    @typing.overload
    def insert_events(self, input_buf: metavision_sdk_base.EventCDBuffer) -> None:
        """
        This function inserts events from an event buffer into the rolling buffer based on the current mode (N_US or N_EVENTS)
            :input_buf: input chunk of events
        """
    def size(self) -> int:
        """Returns the current number of events stored in the buffer."""
def getColor(palette: ColorPalette, type: ColorType) -> tuple[float, float, float]:
    ...
def hsv2rgb(h: typing.SupportsFloat | typing.SupportsIndex, s: typing.SupportsFloat | typing.SupportsIndex, v: typing.SupportsFloat | typing.SupportsIndex) -> tuple[float, float, float]:
    ...
def rgb2hsv(r: typing.SupportsFloat | typing.SupportsIndex, g: typing.SupportsFloat | typing.SupportsIndex, b: typing.SupportsFloat | typing.SupportsIndex) -> tuple[float, float, float]:
    ...
Auxiliary: ColorType
Background: ColorType
CoolWarm: ColorPalette
Dark: ColorPalette
EventBbox: numpy.dtypes.VoidDType
EventTrackedBox: numpy.dtypes.VoidDType
Gray: ColorPalette
Light: ColorPalette
Negative: ColorType
Positive: ColorType
