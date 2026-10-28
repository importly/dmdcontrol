from __future__ import annotations
import collections.abc
import numpy
import numpy.dtypes
import typing
__all__: list[str] = ['EventCD', 'EventCDBuffer', 'EventExtTrigger', 'EventExtTriggerBuffer', 'GenericHeader', 'RawEventFrameDiff', 'RawEventFrameHisto', 'SoftwareInfo']
class _EventCD_decode:
    def __init__(self, arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex, arg2: typing.SupportsInt | typing.SupportsIndex, arg3: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class EventCDBuffer:
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
    def _buffer_info(self) -> buffer_info:
        ...
    def numpy(self, copy: bool = False) -> numpy.typing.NDArray[_EventCD_decode]:
        """
           :copy: if True, allocates new memory and returns a copy of the events. If False, use the same memory
        """
    def resize(self, size: typing.SupportsInt | typing.SupportsIndex) -> None:
        """
        resizes the buffer to the specified size
        
           :size: the new size of the buffer
        """
class _EventExtTrigger_decode:
    def __init__(self, arg0: typing.SupportsInt | typing.SupportsIndex, arg1: typing.SupportsInt | typing.SupportsIndex, arg2: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
class EventExtTriggerBuffer:
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
    def _buffer_info(self) -> buffer_info:
        ...
    def numpy(self, copy: bool = False) -> numpy.typing.NDArray[_EventExtTrigger_decode]:
        """
           :copy: if True, allocates new memory and returns a copy of the events. If False, use the same memory
        """
    def resize(self, size: typing.SupportsInt | typing.SupportsIndex) -> None:
        """
        resizes the buffer to the specified size
        
           :size: the new size of the buffer
        """
class RawEventFrameDiff:
    def __init__(self, height: typing.SupportsInt | typing.SupportsIndex, width: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def buffer_size(self) -> int:
        ...
    def numpy(self) -> numpy.typing.NDArray[numpy.int8]:
        """
        Converts to a numpy array
        """
class RawEventFrameHisto:
    def __init__(self, height: typing.SupportsInt | typing.SupportsIndex, width: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def buffer_size(self) -> int:
        ...
class SoftwareInfo:
    """Stores information about the version of the software."""
    def __init__(self, version_major: typing.SupportsInt | typing.SupportsIndex, version_minor: typing.SupportsInt | typing.SupportsIndex, version_patch: typing.SupportsInt | typing.SupportsIndex, version_suffix_string: str, vcs_branch: str, vcs_commit: str, vcs_date: str) -> None:
        ...
    def get_vcs_branch(self) -> str:
        """Returns version control software (vcs) branch."""
    def get_vcs_commit(self) -> str:
        """Returns version control software (vcs) commit."""
    def get_vcs_date(self) -> str:
        """Returns version control software (vcs) commit’s date."""
    def get_version(self) -> str:
        """Returns version as a string."""
    def get_version_major(self) -> int:
        """Returns major version number."""
    def get_version_minor(self) -> int:
        """Returns minor version number."""
    def get_version_patch(self) -> int:
        """Returns patch version number."""
    def get_version_suffix(self) -> str:
        """Returns version suffix string."""
class _BufferInfo:
    format: str
    def __init__(self) -> None:
        ...
    def ptr(self) -> int:
        ...
    def ptr_hex(self) -> str:
        ...
    def to_dict(self) -> dict:
        ...
    @property
    def itemsize(self) -> int:
        ...
    @itemsize.setter
    def itemsize(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def ndim(self) -> int:
        ...
    @ndim.setter
    def ndim(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def shape(self) -> list[int]:
        ...
    @shape.setter
    def shape(self, arg0: collections.abc.Sequence[typing.SupportsInt | typing.SupportsIndex]) -> None:
        ...
    @property
    def size(self) -> int:
        ...
    @size.setter
    def size(self, arg0: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    @property
    def strides(self) -> list[int]:
        ...
    @strides.setter
    def strides(self, arg0: collections.abc.Sequence[typing.SupportsInt | typing.SupportsIndex]) -> None:
        ...
class GenericHeader:
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, arg0: dict) -> None:
        """
        Args:
         dict (dictionary): a python dictionary holding key value pairs of string types.
        """
    @typing.overload
    def __init__(self, arg0: str) -> None:
        """
        Args:
         filename (str): name of the file to open
        """
    def add_date(self) -> None:
        """Adds the current date and time to the header (in the format Y-m-d H:M:S)."""
    def empty(self) -> bool:
        """Returns if the header is empty."""
    def get_date(self) -> str:
        """Gets the date and time at which the associated file was recorded."""
    def get_field(self, key: str) -> str:
        """Gets the value associated to the input key."""
    def get_header_map(self) -> dict[str, str]:
        """Gets the HeaderMap holding the header information."""
    def remove_date(self) -> None:
        """Removes the date if there was any in the header."""
    def remove_field(self, key: str) -> None:
        """Remove the input field (if exists)"""
    def set_field(self, key: str, value: str) -> None:
        """Adds a new field in the header."""
    def to_string(self) -> str:
        """Serializes the header map."""
def _buffer_info(arg0: numpy.ndarray) -> _BufferInfo:
    ...
EventCD: numpy.dtypes.VoidDType
EventExtTrigger: numpy.dtypes.VoidDType
