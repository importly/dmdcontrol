from __future__ import annotations
import collections.abc
import metavision_hal
import metavision_sdk_base
import numpy.typing
import os
import pathlib
import typing
__all__: list[str] = ['Camera', 'CameraStreamSlicer', 'FileConfigHints', 'HDF5EventFileWriter', 'IDENTITY', 'MET_AUTOMATIC', 'MET_N_EVENTS', 'MET_N_US', 'MIXED', 'NOT_MET', 'N_EVENTS', 'N_US', 'RAWEvt2EventFileWriter', 'RValueCamera', 'ReslicingConditionStatus', 'ReslicingConditionType', 'Slice', 'SliceCondition', 'SyncedCameraStreamsSlicer', 'SyncedCameraSystemBuilder', 'SyncedCameraSystemFactory', 'SyncedSlice']
class FileConfigHints:
    """Class represented by a map of string key/value pair, used to control how a file is read by the Camera class."""
    def __init__(self) -> None:
        ...
    def get(self, key: str, def_: str = '') -> str:
        """Gets the (typed) value for a named key in the config dictionary if it exists and can be extracted from the corresponding value safely or the provided default value."""
    @typing.overload
    def max_memory(self) -> int:
        """Gets the maximum memory used (if applicable) setting."""
    @typing.overload
    def max_memory(self, max_memory: typing.SupportsInt | typing.SupportsIndex) -> FileConfigHints:
        """Named constructor for the max memory setting."""
    @typing.overload
    def max_memory(self, max_read_per_op: typing.SupportsInt | typing.SupportsIndex) -> FileConfigHints:
        """Named constructor for the max read size per read operation."""
    def max_read_per_op(self) -> int:
        """Gets the maximum read size (if applicable) setting."""
    @typing.overload
    def real_time_playback(self) -> bool:
        """Gets the real-time playback status."""
    @typing.overload
    def real_time_playback(self, enabled: bool) -> FileConfigHints:
        """Named constructor for the real time playback status."""
    def set(self, key: str, value: str) -> None:
        """Sets a value for a named key in the config dictionary This is an overloaded member function, provided for convenience. It differs from the above function only in what argument(s) it accepts."""
    @typing.overload
    def time_shift(self) -> bool:
        """Gets the timeshift status."""
    @typing.overload
    def time_shift(self, enabled: bool) -> FileConfigHints:
        """Named constructor for the time shift status."""
class RValueCamera:
    pass
class Camera:
    """Main class for the camera interface."""
    @staticmethod
    def from_file(file_path: os.PathLike | str | bytes, hints: FileConfigHints = ...) -> Camera:
        """Initializes a camera instance from a file."""
    @staticmethod
    @typing.overload
    def from_first_available() -> Camera:
        """Initializes a camera instance from the first available camera plugged on the system."""
    @staticmethod
    @typing.overload
    def from_first_available(config: metavision_hal.DeviceConfig) -> Camera:
        """Initializes a camera instance from the first available camera plugged on the system."""
    @staticmethod
    @typing.overload
    def from_serial(serial: str) -> Camera:
        """Initializes a camera instance from a ‘serial’ number."""
    @staticmethod
    @typing.overload
    def from_serial(serial: str, config: metavision_hal.DeviceConfig) -> Camera:
        """Initializes a camera instance from a ‘serial’ number."""
    def get_device(self) -> metavision_hal.Device:
        """Gets corresponding Device in HAL library."""
    def height(self) -> int:
        """
        Returns the height of the camera
        """
    def load(self, path: os.PathLike | str | bytes) -> bool:
        """Loads the camera settings from a given file."""
    def move(self) -> RValueCamera:
        ...
    def save(self, path: os.PathLike | str | bytes) -> bool:
        """Saves the camera settings to a given file."""
    def width(self) -> int:
        """
        Returns the width of the camera
        """
class Slice:
    """Structure representing a slice of events and triggers."""
    __hash__: typing.ClassVar[None] = None
    def __eq__(self, other: Slice) -> bool:
        ...
    def __init__(self) -> None:
        ...
    @property
    def events(self) -> numpy.typing.NDArray[metavision_sdk_base._EventCD_decode]:
        """Events in the slice. Fields: x, y (pixel), p (1 = brighter, 0 = darker), t (µs)."""
    @property
    def n_events(self) -> int:
        """Number of CD events in the slice."""
    @property
    def status(self) -> typing.Any:
        """Status indicating how the slice was completed."""
    @property
    def t(self) -> int:
        """Timestamp of the slice."""
    @property
    def triggers(self) -> numpy.typing.NDArray[metavision_sdk_base._EventExtTrigger_decode]:
        """Triggers in the slice. Fields: p (1 = rising edge, 0 = falling edge), t (µs), id (trigger channel)."""
class ReslicingConditionType:
    """
    Members:
    
      IDENTITY
    
      N_EVENTS
    
      N_US
    
      MIXED
    """
    IDENTITY: typing.ClassVar[ReslicingConditionType]
    MIXED: typing.ClassVar[ReslicingConditionType]
    N_EVENTS: typing.ClassVar[ReslicingConditionType]
    N_US: typing.ClassVar[ReslicingConditionType]
    __members__: typing.ClassVar[dict[str, ReslicingConditionType]]
    @typing.overload
    def __eq__(self, other: ReslicingConditionType) -> bool:
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
    def __ne__(self, other: ReslicingConditionType) -> bool:
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
class ReslicingConditionStatus:
    """
    Members:
    
      NOT_MET
    
      MET_AUTOMATIC
    
      MET_N_EVENTS
    
      MET_N_US
    """
    MET_AUTOMATIC: typing.ClassVar[ReslicingConditionStatus]
    MET_N_EVENTS: typing.ClassVar[ReslicingConditionStatus]
    MET_N_US: typing.ClassVar[ReslicingConditionStatus]
    NOT_MET: typing.ClassVar[ReslicingConditionStatus]
    __members__: typing.ClassVar[dict[str, ReslicingConditionStatus]]
    @typing.overload
    def __eq__(self, other: ReslicingConditionStatus) -> bool:
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
    def __ne__(self, other: ReslicingConditionStatus) -> bool:
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
class SliceCondition:
    type: ReslicingConditionType
    @staticmethod
    def make_identity() -> SliceCondition:
        ...
    @staticmethod
    def make_mixed(delta_ts: typing.SupportsInt | typing.SupportsIndex, delta_n_events: typing.SupportsInt | typing.SupportsIndex) -> SliceCondition:
        ...
    @staticmethod
    def make_n_events(delta_n_events: typing.SupportsInt | typing.SupportsIndex) -> SliceCondition:
        ...
    @staticmethod
    def make_n_us(delta_ts: typing.SupportsInt | typing.SupportsIndex) -> SliceCondition:
        ...
    def __init__(self) -> None:
        ...
    def is_tracking_duration(self) -> bool:
        ...
    def is_tracking_events_count(self) -> bool:
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
class CameraStreamSlicer:
    """Class that slices a stream of events and triggers according to a given condition."""
    def __init__(self, rvalue_camera: RValueCamera, slice_condition: SliceCondition = ..., max_queue_size: typing.SupportsInt | typing.SupportsIndex = 5) -> None:
        ...
    def __iter__(self) -> collections.abc.Iterator[Slice]:
        ...
    def begin(self) -> typing.Any:
        """Starts the camera stream and returns an iterator to the first slice."""
    def camera(self) -> Camera:
        """Returns the underlying camera instance."""
class HDF5EventFileWriter:
    ...
    def __init__(self, path: os.PathLike | str | bytes = '', metadata_map: collections.abc.Mapping[str, str] = {}) -> None:
        ...
    def add_cd_events(self, events: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Adds an array of EventCD to write to the file
        
        Args:
            events: numpy array of EventCD
        """
    def add_ext_trigger_events(self, events: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventExtTrigger_decode]) -> None:
        """
        Adds an array of EventExtTrigger to write to the file
        
        Args:
            events: numpy array of EventExtTrigger
        """
    def add_metadata(self, key: str, value: str) -> None:
        """Adds metadata to the file."""
    def add_metadata_map_from_camera(self, camera: Camera) -> None:
        """Adds metadata to the file from a Camera instance."""
    def close(self) -> None:
        """Close the writer."""
    def flush(self) -> None:
        """Try to flush any data not yet written to disk."""
    def is_open(self) -> bool:
        """Check that the writer is currently opened and ready to write data."""
    def open(self, path: os.PathLike | str | bytes) -> None:
        """Open the writer with specified path."""
class RAWEvt2EventFileWriter:
    """EventFileWriter specialized class to write events to a RAW EVT2 file."""
    def __init__(self, stream_width: typing.SupportsInt | typing.SupportsIndex, stream_height: typing.SupportsInt | typing.SupportsIndex, path: os.PathLike | str | bytes = ..., enable_trigger_support: bool = False, metadata_map: collections.abc.Mapping[str, str] = {}, max_events_add_latency: typing.SupportsInt | typing.SupportsIndex = 9223372036854775807) -> None:
        ...
    def add_cd_events(self, events: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventCD_decode]) -> None:
        """
        Adds an array of EventCD to write to the file
        
        Args:
            events: numpy array of EventCD
        """
    def add_ext_trigger_events(self, events: typing.Annotated[numpy.typing.ArrayLike, metavision_sdk_base._EventExtTrigger_decode]) -> None:
        """
        Adds an array of EventExtTrigger to write to the file
        
        Args:
            events: numpy array of EventExtTrigger
        """
    def add_metadata(self, key: str, value: str) -> None:
        """Adds metadata to the file."""
    def close(self) -> None:
        """Close the writer."""
    def flush(self) -> None:
        """Try to flush any data not yet written to disk."""
    def is_open(self) -> bool:
        """Check that the writer is currently opened and ready to write data."""
    def open(self, path: os.PathLike | str | bytes) -> None:
        """Open the writer with specified path."""
class SyncedSlice:
    """A slice of synchronized events from a master and slave cameras."""
    __hash__: typing.ClassVar[None] = None
    def __eq__(self, other: SyncedSlice) -> bool:
        ...
    def __init__(self) -> None:
        ...
    @property
    def master_events(self) -> numpy.typing.NDArray[metavision_sdk_base._EventCD_decode]:
        """Events in the master slice."""
    @property
    def master_triggers(self) -> numpy.typing.NDArray[metavision_sdk_base._EventExtTrigger_decode]:
        """Triggers in the master slice."""
    @property
    def n_events(self) -> int:
        """Number of events in the master slice."""
    @property
    def slave_events(self) -> list:
        """Events in the slave slices."""
    @property
    def status(self) -> ReslicingConditionStatus:
        """Status indicating how the slice was completed."""
    @property
    def t(self) -> int:
        """Timestamp of the slice."""
class SyncedCameraStreamsSlicer:
    """Class for slicing event streams from master and slave cameras based on a condition."""
    def __init__(self, camera: RValueCamera, Cameras: list, slice_condition: SliceCondition = ..., max_queue_size: typing.SupportsInt | typing.SupportsIndex = 5) -> None:
        ...
    def __iter__(self) -> collections.abc.Iterator[SyncedSlice]:
        ...
    def begin(self) -> typing.Any:
        """Starts the camera streams and returns an iterator to the first slice."""
    def master(self) -> Camera:
        """Returns the underlying master camera instance."""
    def slave(self, i: typing.SupportsInt | typing.SupportsIndex) -> Camera:
        """Returns the underlying slave camera instance."""
    def slaves_count(self) -> int:
        """Returns the number of slave cameras."""
class SyncedCameraSystemBuilder:
    """Builder class to create a synced camera system."""
    def __init__(self) -> None:
        ...
    def add_live_camera_parameters(self, serial_number: str, device_config: metavision_hal.DeviceConfig = ..., settings_file_path: os.PathLike | str | bytes | None = None) -> None:
        """Adds live camera parameters to the builder."""
    def add_record_path(self, record_path: os.PathLike | str | bytes) -> SyncedCameraSystemBuilder:
        """Adds a path to a record file."""
    def build(self) -> tuple[Camera, list[Camera]]:
        """Builds the synced camera system."""
    def set_file_config_hints(self, file_config_hints: FileConfigHints) -> SyncedCameraSystemBuilder:
        """Sets the file config hints."""
    def set_record(self, record: bool) -> SyncedCameraSystemBuilder:
        """Sets whether the system should record the live events or not."""
    def set_record_dir(self, record_dir: os.PathLike | str | bytes) -> SyncedCameraSystemBuilder:
        """Sets the directory where the events will be recorded."""
class SyncedCameraSystemFactory:
    ...
    class LiveCameraParameters:
        """Parameters to create a live camera."""
        def __init__(self) -> None:
            ...
        @property
        def device_config(self) -> metavision_hal.DeviceConfig:
            """Device configuration."""
        @device_config.setter
        def device_config(self, arg0: metavision_hal.DeviceConfig) -> None:
            ...
        @property
        def serial_number(self) -> str:
            """Serial number of the camera."""
        @serial_number.setter
        def serial_number(self, arg0: str) -> None:
            ...
        @property
        def settings_file_path(self) -> pathlib.Path | None:
            """Optional path to a camera settings file."""
        @settings_file_path.setter
        def settings_file_path(self, arg0: os.PathLike | str | bytes | None) -> None:
            ...
    class LiveParameters:
        """Parameters to create a synced live camera system."""
        def __init__(self) -> None:
            ...
        @property
        def master_parameters(self) -> SyncedCameraSystemFactory.LiveCameraParameters:
            """Parameters for the master camera."""
        @master_parameters.setter
        def master_parameters(self, arg0: SyncedCameraSystemFactory.LiveCameraParameters) -> None:
            ...
        @property
        def record(self) -> bool:
            """True to record the events, false otherwise."""
        @record.setter
        def record(self, arg0: bool) -> None:
            ...
        @property
        def record_dir(self) -> pathlib.Path | None:
            """Optional directory where the events will be recorded."""
        @record_dir.setter
        def record_dir(self, arg0: os.PathLike | str | bytes | None) -> None:
            ...
        @property
        def slave_parameters(self) -> list[SyncedCameraSystemFactory.LiveCameraParameters]:
            """Parameters for the slave cameras."""
        @slave_parameters.setter
        def slave_parameters(self, arg0: collections.abc.Sequence[SyncedCameraSystemFactory.LiveCameraParameters]) -> None:
            ...
    class OfflineParameters:
        """Parameters to create a synced offline camera system."""
        def __init__(self) -> None:
            ...
        @property
        def file_config_hints(self) -> FileConfigHints:
            """Hints to configure the file reading."""
        @file_config_hints.setter
        def file_config_hints(self, arg0: FileConfigHints) -> None:
            ...
        @property
        def master_file_path(self) -> pathlib.Path:
            """Path to the master record."""
        @master_file_path.setter
        def master_file_path(self, arg0: os.PathLike | str | bytes) -> None:
            ...
        @property
        def slave_file_paths(self) -> list[pathlib.Path]:
            """Paths to the slave records."""
        @slave_file_paths.setter
        def slave_file_paths(self, arg0: collections.abc.Sequence[os.PathLike | str | bytes]) -> None:
            ...
    @staticmethod
    @typing.overload
    def build(parameters: typing.Any) -> tuple[Camera, list[Camera]]:
        """Builds a synced camera system with live cameras."""
    @staticmethod
    @typing.overload
    def build(parameters: typing.Any) -> tuple[Camera, list[Camera]]:
        """Builds a synced camera system with offline cameras."""
    def __init__(self) -> None:
        ...
IDENTITY: ReslicingConditionType
MET_AUTOMATIC: ReslicingConditionStatus
MET_N_EVENTS: ReslicingConditionStatus
MET_N_US: ReslicingConditionStatus
MIXED: ReslicingConditionType
NOT_MET: ReslicingConditionStatus
N_EVENTS: ReslicingConditionType
N_US: ReslicingConditionType
