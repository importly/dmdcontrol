from __future__ import annotations
import collections.abc
import metavision_sdk_base
import os
import typing
__all__: list[str] = ['CameraDescription', 'ConnectionType', 'Deprecated', 'Device', 'DeviceConfig', 'DeviceConfigOption', 'DeviceDiscovery', 'I_AntiFlickerModule', 'I_CameraSynchronization', 'I_Decoder', 'I_DigitalCrop', 'I_DigitalEventMask', 'I_ErcModule', 'I_EventDecoder_EventCD', 'I_EventDecoder_EventExtTrigger', 'I_EventFrameDecoder_RawEventFrameDiff', 'I_EventFrameDecoder_RawEventFrameHisto', 'I_EventRateActivityFilterModule', 'I_EventTrailFilterModule', 'I_EventsStream', 'I_Geometry', 'I_HALSoftwareInfo', 'I_HW_Identification', 'I_HW_Register', 'I_LL_Biases', 'I_Monitoring', 'I_PixelMask', 'I_PluginSoftwareInfo', 'I_ROI', 'I_RoiPixelMask', 'I_TriggerIn', 'I_TriggerOut', 'LL_Bias_Info', 'PluginCameraDescription', 'RawBuffer', 'RawFileConfig', 'RawFileHeader', 'SensorInfo', 'get_hal_software_info']
class Deprecated(Exception):
    pass
class ConnectionType:
    """
    Members:
    
      MIPI_LINK
    
      USB_LINK
    
      NETWORK_LINK
    
      PROPRIETARY_LINK
    """
    MIPI_LINK: typing.ClassVar[ConnectionType]
    NETWORK_LINK: typing.ClassVar[ConnectionType]
    PROPRIETARY_LINK: typing.ClassVar[ConnectionType]
    USB_LINK: typing.ClassVar[ConnectionType]
    __members__: typing.ClassVar[dict[str, ConnectionType]]
    @typing.overload
    def __eq__(self, other: ConnectionType) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
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
    def __ne__(self, other: ConnectionType) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
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
class DeviceDiscovery:
    """Discovery of connected device."""
    @staticmethod
    def list() -> list[str]:
        """Lists serial numbers of available sources, including remote cameras."""
    @staticmethod
    def list_available_sources() -> list[...]:
        """Lists available sources, including remote cameras."""
    @staticmethod
    def list_available_sources_local() -> list[...]:
        """Lists only local available sources."""
    @staticmethod
    def list_available_sources_remote() -> list[...]:
        """Lists only remote available sources."""
    @staticmethod
    def list_device_config_options(serial: str) -> dict[str, ...]:
        """Lists DeviceConfig options supported by the camera."""
    @staticmethod
    def list_local() -> list[str]:
        """Lists serial numbers of local available sources."""
    @staticmethod
    def list_remote() -> list[str]:
        """Lists serial numbers of remote available sources."""
    @staticmethod
    @typing.overload
    def open(serial: str) -> Device | None:
        """Builds a new Device."""
    @staticmethod
    @typing.overload
    def open(serial: str, config: typing.Any) -> Device | None:
        """Builds a new Device."""
    @staticmethod
    @typing.overload
    def open_raw_file(raw_file: os.PathLike | str | bytes) -> Device | None:
        """Builds a new Device from file."""
    @staticmethod
    @typing.overload
    def open_raw_file(raw_file: os.PathLike | str | bytes, file_config: typing.Any) -> Device | None:
        """Builds a new Device from file."""
class RawFileConfig:
    """RAW files configuration’s options."""
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: RawFileConfig) -> None:
        ...
    @property
    def build_index(self) -> bool:
        """True if indexing should be performed when opening the file Alternatively, indexing can still be requested by calling I_EventsStream::index directly"""
    @build_index.setter
    def build_index(self, arg0: bool) -> None:
        ...
    @property
    def do_time_shifting(self) -> bool:
        """Take the first timer high of the file as origin of time."""
    @do_time_shifting.setter
    def do_time_shifting(self, arg0: bool) -> None:
        ...
    @property
    def n_events_to_read(self) -> int:
        """Number of events_byte_size blocks to read. At each read, n_events_to_read_*sizeof(RAW_event) bytes are read. :warning: sizeof(RAW_event) is defined by the events format contained in the RAW file read."""
    @n_events_to_read.setter
    def n_events_to_read(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def n_read_buffers(self) -> int:
        """The maximum number of buffers to allocate and use for reading. Each buffer contains at most n_events_to_read_ RAW events. The maximum memory allocated to read the RAW file will be read_buffers_count_ * n_events_to_read_ * sizeof(RAW_event). One can use this parameters to have a finer control on offline memory usage"""
    @n_read_buffers.setter
    def n_read_buffers(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class I_TriggerOut:
    """Internal interface for trigger out signal configuration."""
    def disable(self) -> bool:
        """Disables the trigger out."""
    def enable(self) -> bool:
        """Enables the trigger out."""
    def set_duty_cycle(self, period_ratio: typing.SupportsFloat | typing.SupportsIndex) -> bool:
        """Sets the duty cycle of the trigger out signal i.e. the pulse duration."""
    def set_period(self, period_us: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets the trigger out signal period (in us)"""
class I_TriggerIn:
    """Interface to handle external trigger signals."""
    class Channel:
        """
        Members:
        
          MAIN
        
          AUX
        
          LOOPBACK
        """
        AUX: typing.ClassVar[I_TriggerIn.Channel]
        LOOPBACK: typing.ClassVar[I_TriggerIn.Channel]
        MAIN: typing.ClassVar[I_TriggerIn.Channel]
        __members__: typing.ClassVar[dict[str, I_TriggerIn.Channel]]
        @typing.overload
        def __eq__(self, other: I_TriggerIn.Channel) -> bool:
            ...
        @typing.overload
        def __eq__(self, other: typing.Any) -> bool:
            ...
        @typing.overload
        def __ge__(self, other: I_TriggerIn.Channel) -> bool:
            ...
        @typing.overload
        def __ge__(self, other: typing.Any) -> None:
            ...
        def __getstate__(self) -> int:
            ...
        @typing.overload
        def __gt__(self, other: I_TriggerIn.Channel) -> bool:
            ...
        @typing.overload
        def __gt__(self, other: typing.Any) -> None:
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
        def __le__(self, other: I_TriggerIn.Channel) -> bool:
            ...
        @typing.overload
        def __le__(self, other: typing.Any) -> None:
            ...
        @typing.overload
        def __lt__(self, other: I_TriggerIn.Channel) -> bool:
            ...
        @typing.overload
        def __lt__(self, other: typing.Any) -> None:
            ...
        @typing.overload
        def __ne__(self, other: I_TriggerIn.Channel) -> bool:
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
    def disable(self, channel: I_TriggerIn.Channel) -> bool:
        """Disables external trigger monitoring."""
    def enable(self, channel: I_TriggerIn.Channel) -> bool:
        """Enables external trigger monitoring."""
    def get_available_channels(self) -> dict[I_TriggerIn.Channel, int]:
        """Returns the map of available channels."""
    def is_enabled(self, channel: I_TriggerIn.Channel) -> bool:
        """Checks if external trigger monitoring is enabled."""
class I_ROI:
    """Interface facility for ROI (Region Of Interest)"""
    class Mode:
        """
        Members:
        
          ROI
        
          RONI
        """
        ROI: typing.ClassVar[I_ROI.Mode]
        RONI: typing.ClassVar[I_ROI.Mode]
        __members__: typing.ClassVar[dict[str, I_ROI.Mode]]
        @typing.overload
        def __eq__(self, other: I_ROI.Mode) -> bool:
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
        def __ne__(self, other: I_ROI.Mode) -> bool:
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
    class Window:
        """Defines a simple rectangular window."""
        @typing.overload
        def __init__(self, arg0: I_ROI.Window) -> None:
            ...
        @typing.overload
        def __init__(self, arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex, arg2: typing.SupportsInt | typing.SupportsIndex, arg3: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        def to_string(self) -> str:
            """Returns the window as a string."""
        @property
        def height(self) -> int:
            ...
        @height.setter
        def height(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        @property
        def width(self) -> int:
            ...
        @width.setter
        def width(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        @property
        def x(self) -> int:
            ...
        @x.setter
        def x(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        @property
        def y(self) -> int:
            ...
        @y.setter
        def y(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
    def enable(self, enable: bool) -> bool:
        """Applies ROI."""
    def get_max_supported_windows_count(self) -> int:
        """Gets the maximum number of windows."""
    def set_lines(self, cols: list, rows: list) -> None:
        ...
    def set_mode(self, mode: typing.Any) -> bool:
        """Sets the window mode."""
    def set_window(self, roi: typing.Any) -> bool:
        """Sets a window."""
    def set_windows(self, roi_list: list) -> None:
        ...
class I_PluginSoftwareInfo:
    """Provides information about the Plugin software."""
    def get_plugin_integrator_name(self) -> str:
        """Gets plugin integrator name."""
    def get_plugin_name(self) -> str:
        """Gets plugin name."""
    def get_software_info(self) -> metavision_sdk_base.SoftwareInfo:
        """Gets HAL’s software information."""
class I_EventTrailFilterModule:
    """Noise filter module."""
    class Type:
        """
        Members:
        
          TRAIL
        
          STC_CUT_TRAIL
        
          STC_KEEP_TRAIL
        """
        STC_CUT_TRAIL: typing.ClassVar[I_EventTrailFilterModule.Type]
        STC_KEEP_TRAIL: typing.ClassVar[I_EventTrailFilterModule.Type]
        TRAIL: typing.ClassVar[I_EventTrailFilterModule.Type]
        __members__: typing.ClassVar[dict[str, I_EventTrailFilterModule.Type]]
        @typing.overload
        def __eq__(self, other: I_EventTrailFilterModule.Type) -> bool:
            ...
        @typing.overload
        def __eq__(self, other: typing.Any) -> bool:
            ...
        @typing.overload
        def __ge__(self, other: I_EventTrailFilterModule.Type) -> bool:
            ...
        @typing.overload
        def __ge__(self, other: typing.Any) -> None:
            ...
        def __getstate__(self) -> int:
            ...
        @typing.overload
        def __gt__(self, other: I_EventTrailFilterModule.Type) -> bool:
            ...
        @typing.overload
        def __gt__(self, other: typing.Any) -> None:
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
        def __le__(self, other: I_EventTrailFilterModule.Type) -> bool:
            ...
        @typing.overload
        def __le__(self, other: typing.Any) -> None:
            ...
        @typing.overload
        def __lt__(self, other: I_EventTrailFilterModule.Type) -> bool:
            ...
        @typing.overload
        def __lt__(self, other: typing.Any) -> None:
            ...
        @typing.overload
        def __ne__(self, other: I_EventTrailFilterModule.Type) -> bool:
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
    def enable(self, state: bool) -> bool:
        """Enables the EventTrailFilterModule with previously configured settings. Filtering type and threshold should be set before enabling."""
    def get_available_types(self) -> set[I_EventTrailFilterModule.Type]:
        """Returns the set of available types of filters."""
    def get_max_supported_threshold(self) -> int:
        """Gets the maximum supported value for event trail filtering threshold delay (in microseconds)"""
    def get_min_supported_threshold(self) -> int:
        """Gets the minimum supported value for event trail filtering threshold delay (in microseconds)"""
    def get_threshold(self) -> int:
        """Gets the event trail filtering threshold delay (in microseconds)"""
    def get_type(self) -> I_EventTrailFilterModule.Type:
        """Gets the event trail filtering type."""
    def is_enabled(self) -> bool:
        """Returns EventTrailFilterModule activation state."""
    def set_threshold(self, threshold: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets the event trail filtering threshold delay."""
    def set_type(self, type: I_EventTrailFilterModule.Type) -> bool:
        """Sets the event trail filtering type."""
class I_RoiPixelMask:
    """Interface facility for ROI (Region Of Interest) pixel mask."""
    def apply_pixels(self) -> None:
        """Apply pixels configuration to sensor Pixels selected to be masked with the set_pixel function are applied to the sensor hardware."""
    def set_pixel(self, arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex, arg2: bool) -> bool:
        """Set individual pixel ROI mask The pixel coordinates are stored in the driver and will be sent to the sensor when apply_pixels function is called."""
class I_Monitoring:
    """Interface facility to monitor sensor parameters (such as temperature and illumination)"""
    def get_illumination(self) -> int:
        """Gets illumination."""
    def get_pixel_dead_time(self) -> int:
        """Gets Pixel Dead Time (aka. "refractory period"). This is the minimum time latency between the generation of 2 events by a pixel."""
    def get_temperature(self) -> int:
        """Gets temperature."""
class I_LL_Biases:
    """Interface facility for Low Level Biases."""
    def get(self, bias_name: str) -> int:
        """Gets bias value."""
    def get_all_biases(self) -> dict:
        """Gets all biases values."""
    def get_bias_info(self, bias_name: str) -> typing.Any:
        """
        Gets bias metadata.
        
            :bias_name: Name of the bias whose metadata to get
        
            :return: Metadata of the bias
        """
    def set(self, bias_name: str, bias_value: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets bias value."""
class LL_Bias_Info:
    """Base class used to represent Low Level Biases metadata."""
    def get_bias_allowed_range(self) -> tuple[int, int]:
        """Gets the bias’ range of allowed values."""
    def get_bias_range(self) -> tuple[int, int]:
        """Gets the bias’ range of valid values."""
    def get_bias_recommended_range(self) -> tuple[int, int]:
        """Gets the bias’ range of recommended values."""
    def get_category(self) -> str:
        """Gets the bias’ category."""
    def get_description(self) -> str:
        """Gets the bias’ description."""
    def is_modifiable(self) -> bool:
        """Gets the bias’ modifiable parameter."""
class I_HW_Register:
    """Interface facility for writing/reading hardware registers."""
    @typing.overload
    def read_register(self, address: typing.SupportsInt | typing.SupportsIndex) -> int:
        """Reads register."""
    @typing.overload
    def read_register(self, address: str) -> int:
        """Reads register."""
    @typing.overload
    def read_register(self, address: str, bitfield: str) -> int:
        """Reads register."""
    @typing.overload
    def write_register(self, address: typing.SupportsInt | typing.SupportsIndex, v: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Writes register."""
    @typing.overload
    def write_register(self, address: str, v: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Writes register."""
    @typing.overload
    def write_register(self, address: str, bitfield: str, v: typing.SupportsInt | typing.SupportsIndex) -> None:
        """Writes register."""
class I_HW_Identification:
    """Facility to provide information about the available system."""
    def get_available_data_encoding_formats(self) -> list[str]:
        """Returns the name of the available data encoding formats."""
    def get_connection_type(self) -> str:
        """Returns the connection with the camera as a string."""
    def get_current_data_encoding_format(self) -> str:
        """Returns the name of the currently used data encoding format."""
    def get_device_config_options(self) -> dict[str, ...]:
        """Lists device config options supported by the camera."""
    def get_header(self) -> typing.Any:
        """Returns a header that can be used to log a RAW file."""
    def get_integrator(self) -> str:
        """Returns the integrator name."""
    def get_sensor_info(self) -> typing.Any:
        """Returns the detail about the available sensor."""
    def get_serial(self) -> str:
        """Returns the serial number of the camera."""
    def get_system_info(self) -> dict:
        """Returns all available information."""
class SensorInfo:
    """Information about the type of sensor available."""
    @property
    def major_version(self) -> int:
        """Sensor Generation."""
    @property
    def minor_version(self) -> int:
        """Sensor Revision."""
    @property
    def name(self) -> str:
        """Sensor Name."""
class I_HALSoftwareInfo:
    """Class that provides information about the HAL software."""
    def get_software_info(self) -> metavision_sdk_base.SoftwareInfo:
        """Gets plugin’s software information."""
class I_Geometry:
    """Class to access information on the size of the sensor."""
    def get_height(self) -> int:
        """Returns height of the sensor in pixels."""
    def get_width(self) -> int:
        """Returns width of the sensor in pixels."""
class I_Decoder:
    """Interface for decoding a stream of events."""
    def add_time_callback(self, cb: typing.Any) -> int:
        """Adds a function that will be called from time to time, giving current timestamp."""
    @typing.overload
    def decode(self, arg0: typing.Any) -> None:
        """
        Decodes raw data. Identifies the events in the buffer and dispatches it to the instance Event Decoder corresponding to each event type
        
        Args:
            RawData: Numpy array of Events
        """
    @typing.overload
    def decode(self, RawData: typing.Any, std: typing.Any) -> None:
        """
        Decodes raw data. Identifies the events in the buffer and dispatches it to the instance Event Decoder corresponding to each event type
        
        Args:
            RawData: Array of events
        """
    def get_last_timestamp(self) -> int:
        """Gets the timestamp of the last event."""
    def remove_callback(self, callback_id: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Removes a previously registered time callback."""
class I_EventsStream:
    """Class for getting buffers from cameras or files."""
    def get_latest_raw_data(self) -> typing.Any:
        """Gets latest raw data from the event buffer."""
    def log_raw_data(self, f: str) -> bool:
        """Enables the logging of the stream of events in the input file f."""
    def poll_buffer(self) -> int:
        """Returns a value that informs if some events are available in the buffer from the camera or the file."""
    def start(self) -> None:
        """Starts streaming events."""
    def stop(self) -> None:
        """Stops streaming events."""
    def stop_log_raw_data(self) -> None:
        """Stops logging RAW data."""
    def wait_next_buffer(self) -> int:
        """Returns a value that informs if some events are available in the buffer from the camera and blocks waiting until more events are available."""
class RawBuffer:
    """Generic Buffer type used by DataTransfer."""
    def size(self) -> int:
        """Accessor to the buffer size."""
class I_EventRateActivityFilterModule:
    """Interface for accessing the sensor event rate activity filter."""
    class thresholds:
        """Band pass filter hysteresis thresholds for event rate activity filter."""
        @property
        def lower_bound_start(self) -> int:
            ...
        @lower_bound_start.setter
        def lower_bound_start(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        @property
        def lower_bound_stop(self) -> int:
            ...
        @lower_bound_stop.setter
        def lower_bound_stop(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        @property
        def upper_bound_start(self) -> int:
            ...
        @upper_bound_start.setter
        def upper_bound_start(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
        @property
        def upper_bound_stop(self) -> int:
            ...
        @upper_bound_stop.setter
        def upper_bound_stop(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
            ...
    def enable(self, enable_filter: bool) -> bool:
        """Enables/disables the event rate activity filter."""
    def get_max_supported_thresholds(self) -> typing.Any:
        """Gets band pass filter hysteresis maximum thresholds configuration."""
    def get_min_supported_thresholds(self) -> typing.Any:
        """Gets band pass filter hysteresis minimum thresholds configuration."""
    def get_thresholds(self) -> typing.Any:
        """Gets band pass filter hysteresis thresholds."""
    def is_enabled(self) -> bool:
        """Returns the event rate activity filter state."""
    def is_thresholds_supported(self) -> typing.Any:
        """Gets band pass filter hysteresis thresholds supported by the sensor."""
    def set_thresholds(self, threshold_ev_s: typing.Any) -> bool:
        """Sets band pass filter hysteresis thresholds."""
class I_EventFrameDecoder_RawEventFrameDiff:
    def add_event_frame_callback(self, arg0: typing.Any) -> int:
        ...
    def decode(self, RawData: typing.Any) -> None:
        """
        Decodes raw data. Identifies the events in the buffer and dispatches it to the instance Event Decoder corresponding to each event type
        
        Args:
            RawData: Numpy array of Event Frames
        """
    def get_height(self) -> int:
        """
        get height
        """
    def get_width(self) -> int:
        """
        get width
        """
    def remove_callback(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
class I_EventFrameDecoder_RawEventFrameHisto:
    def add_event_frame_callback(self, arg0: typing.Any) -> int:
        ...
    def decode(self, RawData: typing.Any) -> None:
        """
        Decodes raw data. Identifies the events in the buffer and dispatches it to the instance Event Decoder corresponding to each event type
        
        Args:
            RawData: Numpy array of Event Frames
        """
    def get_height(self) -> int:
        """
        get height
        """
    def get_width(self) -> int:
        """
        get width
        """
    def remove_callback(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
class I_EventDecoder_EventExtTrigger:
    def add_event_buffer_callback(self, arg0: typing.Any) -> int:
        ...
    def add_event_buffer_native_callback(self, arg0: collections.abc.Callable[[metavision_sdk_base._EventExtTrigger_decode, metavision_sdk_base._EventExtTrigger_decode], None]) -> int:
        """
        const Metavision::EventExtTrigger * end)`.
        """
    def remove_callback(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
class I_EventDecoder_EventCD:
    def add_event_buffer_callback(self, arg0: typing.Any) -> int:
        ...
    def add_event_buffer_native_callback(self, arg0: collections.abc.Callable[[metavision_sdk_base._EventCD_decode, metavision_sdk_base._EventCD_decode], None]) -> int:
        """
        const Metavision::EventCD * end)`.
        """
    def add_event_buffer_nocopy_callback(self, arg0: typing.Any) -> int:
        ...
    def remove_callback(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
class I_ErcModule:
    """Interface for Event Rate Controller (ERC) commands."""
    def enable(self, b: bool) -> bool:
        """Toggles ERC activation."""
    def erc_from_file(self, arg0: str) -> None:
        ...
    def get_cd_event_count(self) -> int:
        """Gets the maximum number of events that ERC will transmit over the count period."""
    def get_cd_event_rate(self) -> int:
        """Gets the CD event rate set point of the ERC."""
    def get_count_period(self) -> int:
        """Gets the count period."""
    def get_max_supported_cd_event_count(self) -> int:
        """Gets the maximum supported value for cd_event_count setting."""
    def get_max_supported_cd_event_rate(self) -> int:
        """Gets the maximum supported value for cd_event_rate setting."""
    def get_min_supported_cd_event_count(self) -> int:
        """Gets the minimum supported value for cd_event_count setting."""
    def get_min_supported_cd_event_rate(self) -> int:
        """Gets the minimum supported value for cd_event_rate setting."""
    def is_enabled(self) -> bool:
        """Returns ERC activation state."""
    def set_cd_event_count(self, event_count: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets the maximum number of events that ERC block should let pass over the count period."""
    def set_cd_event_rate(self, events_per_sec: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets the target CD event rate of the ERC."""
class I_DigitalCrop:
    """Digital Crop feature All pixels outside of the cropping region will be dropped by the sensor."""
    def enable(self, arg0: bool) -> bool:
        """Applies Digital Crop."""
    def get_window_region(self) -> tuple[int, int, int, int]:
        """Gets the digital crop window region currently defined."""
    def is_enabled(self) -> bool:
        """Returns Digital Crop activation state."""
    def set_window_region(self, arg0: tuple[typing.SupportsInt | typing.SupportsIndex, typing.SupportsInt | typing.SupportsIndex, typing.SupportsInt | typing.SupportsIndex, typing.SupportsInt | typing.SupportsIndex], arg1: bool) -> bool:
        """Defines digital crop window region."""
class I_DigitalEventMask:
    """Interface for Digital Event Mask commands."""
    def get_pixel_masks(self) -> list[...]:
        """Get all available masks."""
class I_PixelMask:
    """Interface for Digital Pixel Mask commands."""
    def get_mask(self) -> tuple[int, int, bool]:
        """Get the current mask settings."""
    def set_mask(self, arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex, arg2: bool) -> bool:
        """Set coordinate for the pixel to be masked."""
class I_CameraSynchronization:
    """Facility that controls the camera mode (standalone, master or slave)"""
    def get_mode(self) -> typing.Any:
        """Retrieves Synchronization mode."""
    def set_mode_master(self) -> bool:
        """Sets the camera as master."""
    def set_mode_slave(self) -> bool:
        """Sets the camera as slave."""
    def set_mode_standalone(self) -> bool:
        """Sets the camera in standalone mode."""
class I_AntiFlickerModule:
    """Anti-flicker module."""
    class AntiFlickerMode:
        """
        Members:
        
          BandStop
        
          BandPass
        """
        BandPass: typing.ClassVar[I_AntiFlickerModule.AntiFlickerMode]
        BandStop: typing.ClassVar[I_AntiFlickerModule.AntiFlickerMode]
        __members__: typing.ClassVar[dict[str, I_AntiFlickerModule.AntiFlickerMode]]
        @typing.overload
        def __eq__(self, other: I_AntiFlickerModule.AntiFlickerMode) -> bool:
            ...
        @typing.overload
        def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
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
        def __ne__(self, other: I_AntiFlickerModule.AntiFlickerMode) -> bool:
            ...
        @typing.overload
        def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
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
    def enable(self, b: bool) -> bool:
        """Toggles Anti-flicker activation."""
    def get_band_high_frequency(self) -> int:
        """Gets highest frequency of the band."""
    def get_band_low_frequency(self) -> int:
        """Gets lowest frequency of the band."""
    def get_duty_cycle(self) -> float:
        """Gets the duty cycle for Antiflicker filter."""
    def get_filtering_mode(self) -> typing.Any:
        """Gets filtering mode."""
    def get_frequency_band(self) -> tuple[int, int]:
        """Gets frequency band setting."""
    def get_max_supported_duty_cycle(self) -> float:
        """Gets maximum supported duty cycle value."""
    def get_max_supported_frequency(self) -> int:
        """Gets maximum supported frequency."""
    def get_max_supported_start_threshold(self) -> int:
        """Gets the Antiflicker start threshold maximum supported value."""
    def get_max_supported_stop_threshold(self) -> int:
        """Gets the Antiflicker stop threshold maximum supported value."""
    def get_min_supported_duty_cycle(self) -> float:
        """Gets minimum supported duty cycle value."""
    def get_min_supported_frequency(self) -> int:
        """Gets minimum supported frequency."""
    def get_min_supported_start_threshold(self) -> int:
        """Gets the Antiflicker start threshold minimum supported value."""
    def get_min_supported_stop_threshold(self) -> int:
        """Gets the Antiflicker stop threshold minimum supported value."""
    def get_start_threshold(self) -> int:
        """Gets the Antiflicker start threshold."""
    def get_stop_threshold(self) -> int:
        """Gets the Antiflicker stop threshold."""
    def is_enabled(self) -> bool:
        """Returns Anti-flicker activation state."""
    def set_duty_cycle(self, percent_activity: typing.SupportsFloat | typing.SupportsIndex) -> bool:
        """Sets the duty cycle for Antiflicker filter."""
    def set_filtering_mode(self, arg0: typing.Any) -> bool:
        """Sets the anti-flicker filtering mode."""
    def set_frequency_band(self, min_freq: typing.SupportsInt | typing.SupportsIndex, max_freq: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets anti-flicker parameters."""
    def set_start_threshold(self, threshold: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets the threshold above which Antiflicker should start filtering."""
    def set_stop_threshold(self, threshold: typing.SupportsInt | typing.SupportsIndex) -> bool:
        """Sets the threshold below which Antiflicker should stop filtering."""
class PluginCameraDescription:
    @property
    def connection(self) -> ConnectionType:
        ...
    @property
    def serial(self) -> str:
        ...
class CameraDescription(PluginCameraDescription):
    @property
    def integrator_name(self) -> str:
        ...
    @property
    def plugin_name(self) -> str:
        ...
class DeviceConfig:
    """Class storing a map of (key,values) that can be used to customize how a device should be opened."""
    @staticmethod
    def get_biases_range_check_bypass_key() -> str:
        ...
    @staticmethod
    def get_format_key() -> str:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: DeviceConfig) -> None:
        ...
    def biases_range_check_bypass(self) -> bool:
        """Gets the status of the "bypass biases range check" option."""
    def enable_biases_range_check_bypass(self, enabled: bool) -> None:
        ...
    def format(self) -> str:
        """Gets the event format."""
    def get(self, key: str, def_: str = '') -> str:
        """Gets the (typed) value for a named key in the config dictionary if it exists and can be extracted from the corresponding value safely or the provided default value."""
    def get_bool(self, key: str, def_: bool = True) -> bool:
        """Gets the (typed) value for a named key in the config dictionary if it exists and can be extracted from the corresponding value safely or the provided default value."""
    def get_double(self, key: str, def_: typing.SupportsFloat | typing.SupportsIndex = 0.0) -> float:
        """Gets the (typed) value for a named key in the config dictionary if it exists and can be extracted from the corresponding value safely or the provided default value."""
    def get_int(self, key: str, def_: typing.SupportsInt | typing.SupportsIndex = 0) -> int:
        """Gets the (typed) value for a named key in the config dictionary if it exists and can be extracted from the corresponding value safely or the provided default value."""
    @typing.overload
    def set(self, key: str, value: bool) -> None:
        """Sets a value for a named key in the config dictionary This is an overloaded member function, provided for convenience. It differs from the above function only in what argument(s) it accepts."""
    @typing.overload
    def set(self, key: str, value: str) -> None:
        """
        Sets a value for a named key in the config dictionary This is an overloaded member function, provided for convenience. It differs from the above function only in what argument(s) it accepts.
        """
    @typing.overload
    def set(self, key: str, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        """
        Sets a value for a named key in the config dictionary This is an overloaded member function, provided for convenience. It differs from the above function only in what argument(s) it accepts.
        """
    @typing.overload
    def set(self, key: str, value: typing.SupportsFloat | typing.SupportsIndex) -> None:
        """
        Sets a value for a named key in the config dictionary This is an overloaded member function, provided for convenience. It differs from the above function only in what argument(s) it accepts.
        """
    def set_format(self, format: str) -> None:
        """Sets the event format."""
class DeviceConfigOption:
    """Class representing options allowed for a device configuration entry."""
    class Type:
        """
        Members:
        
          INVALID
        
          BOOLEAN
        
          INT
        
          DOUBLE
        
          STRING
        """
        BOOLEAN: typing.ClassVar[DeviceConfigOption.Type]
        DOUBLE: typing.ClassVar[DeviceConfigOption.Type]
        INT: typing.ClassVar[DeviceConfigOption.Type]
        INVALID: typing.ClassVar[DeviceConfigOption.Type]
        STRING: typing.ClassVar[DeviceConfigOption.Type]
        __members__: typing.ClassVar[dict[str, DeviceConfigOption.Type]]
        @typing.overload
        def __eq__(self, other: DeviceConfigOption.Type) -> bool:
            ...
        @typing.overload
        def __eq__(self, other: typing.Any) -> bool:
            ...
        @typing.overload
        def __ge__(self, other: DeviceConfigOption.Type) -> bool:
            ...
        @typing.overload
        def __ge__(self, other: typing.Any) -> None:
            ...
        def __getstate__(self) -> int:
            ...
        @typing.overload
        def __gt__(self, other: DeviceConfigOption.Type) -> bool:
            ...
        @typing.overload
        def __gt__(self, other: typing.Any) -> None:
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
        def __le__(self, other: DeviceConfigOption.Type) -> bool:
            ...
        @typing.overload
        def __le__(self, other: typing.Any) -> None:
            ...
        @typing.overload
        def __lt__(self, other: DeviceConfigOption.Type) -> bool:
            ...
        @typing.overload
        def __lt__(self, other: typing.Any) -> None:
            ...
        @typing.overload
        def __ne__(self, other: DeviceConfigOption.Type) -> bool:
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
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: bool) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex, arg2: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: typing.SupportsFloat | typing.SupportsIndex, arg1: typing.SupportsFloat | typing.SupportsIndex, arg2: typing.SupportsFloat | typing.SupportsIndex) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: collections.abc.Sequence[str], arg1: str) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: DeviceConfigOption) -> None:
        ...
    def get_default_value(self) -> typing.Any:
        """Gets the set of accepted values."""
    def get_range(self) -> typing.Any:
        """Gets the range of accepted values."""
    def get_values(self) -> list[str]:
        """Gets the set of accepted values."""
    def type(self) -> DeviceConfigOption.Type:
        """Gets the type of this class."""
class RawFileHeader(metavision_sdk_base.GenericHeader):
    """A dedicated class to handle RAW file headers and handle easily their mandatory fields."""
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: RawFileHeader) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: dict) -> None:
        """
        Args:
            dict (dictionary): a python dictionary holding key value pairs of string types.
        """
    def get_camera_integrator_name(self) -> str:
        """Gets the integrator name of the source used to generate the RAW file."""
    def get_plugin_integrator_name(self) -> str:
        """Gets the integrator name of the plugin used to generate the RAW file."""
    def get_plugin_name(self) -> str:
        """Gets the name of the plugin to use to read the RAW file."""
    def set_camera_integrator_name(self, integrator_name: str) -> None:
        """Sets the name of the integrator of the source used to generate the RAW file."""
    def set_plugin_integrator_name(self, integrator_name: str) -> None:
        """Sets the name of the integrator of the plugin used to generate the RAW file."""
    def set_plugin_name(self, plugin_name: str) -> None:
        """Sets the name of the plugin to use to read the RAW file."""
class Device:
    def get_i_antiflicker_module(self) -> I_AntiFlickerModule:
        ...
    def get_i_camera_synchronization(self) -> I_CameraSynchronization:
        ...
    def get_i_digital_crop(self) -> I_DigitalCrop:
        ...
    def get_i_digital_event_mask(self) -> I_DigitalEventMask:
        ...
    def get_i_erc_module(self) -> I_ErcModule:
        ...
    def get_i_event_cd_decoder(self) -> I_EventDecoder_EventCD:
        ...
    def get_i_event_ext_trigger_decoder(self) -> I_EventDecoder_EventExtTrigger:
        ...
    def get_i_event_frame_diff_decoder(self) -> I_EventFrameDecoder_RawEventFrameDiff:
        ...
    def get_i_event_frame_histo_decoder(self) -> I_EventFrameDecoder_RawEventFrameHisto:
        ...
    def get_i_event_rate(self) -> I_EventRateActivityFilterModule:
        ...
    def get_i_event_trail_filter_module(self) -> I_EventTrailFilterModule:
        ...
    def get_i_events_stream(self) -> I_EventsStream:
        ...
    def get_i_events_stream_decoder(self) -> I_Decoder:
        ...
    def get_i_geometry(self) -> I_Geometry:
        ...
    def get_i_hal_software_info(self) -> I_HALSoftwareInfo:
        ...
    def get_i_hw_identification(self) -> I_HW_Identification:
        ...
    def get_i_hw_register(self) -> I_HW_Register:
        ...
    def get_i_ll_biases(self) -> I_LL_Biases:
        ...
    def get_i_monitoring(self) -> I_Monitoring:
        ...
    def get_i_plugin_software_info(self) -> I_PluginSoftwareInfo:
        ...
    def get_i_roi(self) -> I_ROI:
        ...
    def get_i_roi_pixel_mask(self) -> I_RoiPixelMask:
        ...
    def get_i_trigger_in(self) -> I_TriggerIn:
        ...
    def get_i_trigger_out(self) -> I_TriggerOut:
        ...
def get_hal_software_info() -> metavision_sdk_base.SoftwareInfo:
    ...
