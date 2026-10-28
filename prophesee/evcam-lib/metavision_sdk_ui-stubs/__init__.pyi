from __future__ import annotations
import numpy
import typing
__all__: list[str] = ['BaseWindow', 'EventLoop', 'KEY_0', 'KEY_1', 'KEY_2', 'KEY_3', 'KEY_4', 'KEY_5', 'KEY_6', 'KEY_7', 'KEY_8', 'KEY_9', 'KEY_A', 'KEY_APOSTROPHE', 'KEY_B', 'KEY_BACKSLASH', 'KEY_BACKSPACE', 'KEY_C', 'KEY_CAPS_LOCK', 'KEY_COMMA', 'KEY_D', 'KEY_DELETE', 'KEY_DOWN', 'KEY_E', 'KEY_END', 'KEY_ENTER', 'KEY_EQUAL', 'KEY_ESCAPE', 'KEY_F', 'KEY_F1', 'KEY_F10', 'KEY_F11', 'KEY_F12', 'KEY_F13', 'KEY_F14', 'KEY_F15', 'KEY_F16', 'KEY_F17', 'KEY_F18', 'KEY_F19', 'KEY_F2', 'KEY_F20', 'KEY_F21', 'KEY_F22', 'KEY_F23', 'KEY_F24', 'KEY_F25', 'KEY_F3', 'KEY_F4', 'KEY_F5', 'KEY_F6', 'KEY_F7', 'KEY_F8', 'KEY_F9', 'KEY_G', 'KEY_GRAVE_ACCENT', 'KEY_H', 'KEY_HOME', 'KEY_I', 'KEY_INSERT', 'KEY_J', 'KEY_K', 'KEY_KP_0', 'KEY_KP_1', 'KEY_KP_2', 'KEY_KP_3', 'KEY_KP_4', 'KEY_KP_5', 'KEY_KP_6', 'KEY_KP_7', 'KEY_KP_8', 'KEY_KP_9', 'KEY_KP_ADD', 'KEY_KP_DECIMAL', 'KEY_KP_DIVIDE', 'KEY_KP_ENTER', 'KEY_KP_EQUAL', 'KEY_KP_MULTIPLY', 'KEY_KP_SUBTRACT', 'KEY_L', 'KEY_LAST', 'KEY_LEFT', 'KEY_LEFT_ALT', 'KEY_LEFT_BRACKET', 'KEY_LEFT_CONTROL', 'KEY_LEFT_SHIFT', 'KEY_LEFT_SUPER', 'KEY_M', 'KEY_MENU', 'KEY_MINUS', 'KEY_N', 'KEY_NUM_LOCK', 'KEY_O', 'KEY_P', 'KEY_PAGE_DOWN', 'KEY_PAGE_UP', 'KEY_PAUSE', 'KEY_PERIOD', 'KEY_PRINT_SCREEN', 'KEY_Q', 'KEY_R', 'KEY_RIGHT', 'KEY_RIGHT_ALT', 'KEY_RIGHT_BRACKET', 'KEY_RIGHT_CONTROL', 'KEY_RIGHT_SHIFT', 'KEY_RIGHT_SUPER', 'KEY_S', 'KEY_SCROLL_LOCK', 'KEY_SEMICOLON', 'KEY_SLASH', 'KEY_SPACE', 'KEY_T', 'KEY_TAB', 'KEY_U', 'KEY_UNKNOWN', 'KEY_UP', 'KEY_V', 'KEY_W', 'KEY_WORLD_1', 'KEY_WORLD_2', 'KEY_X', 'KEY_Y', 'KEY_Z', 'MOUSE_BUTTON_1', 'MOUSE_BUTTON_2', 'MOUSE_BUTTON_3', 'MOUSE_BUTTON_4', 'MOUSE_BUTTON_5', 'MOUSE_BUTTON_6', 'MOUSE_BUTTON_7', 'MOUSE_BUTTON_8', 'MOUSE_BUTTON_LAST', 'MOUSE_BUTTON_LEFT', 'MOUSE_BUTTON_MIDDLE', 'MOUSE_BUTTON_RIGHT', 'MTWindow', 'PRESS', 'RELEASE', 'REPEAT', 'UIAction', 'UIKeyEvent', 'UIMouseButton', 'Window']
class UIAction:
    """
    Members:
    
      RELEASE
    
      PRESS
    
      REPEAT
    """
    PRESS: typing.ClassVar[UIAction]
    RELEASE: typing.ClassVar[UIAction]
    REPEAT: typing.ClassVar[UIAction]
    __members__: typing.ClassVar[dict[str, UIAction]]
    @typing.overload
    def __and__(self, other: UIAction) -> int:
        ...
    @typing.overload
    def __and__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __eq__(self, other: UIAction) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    @typing.overload
    def __ge__(self, other: UIAction) -> bool:
        ...
    @typing.overload
    def __ge__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    @typing.overload
    def __gt__(self, other: UIAction) -> bool:
        ...
    @typing.overload
    def __gt__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __invert__(self) -> typing.Any:
        ...
    @typing.overload
    def __le__(self, other: UIAction) -> bool:
        ...
    @typing.overload
    def __le__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __lt__(self, other: UIAction) -> bool:
        ...
    @typing.overload
    def __lt__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: UIAction) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    @typing.overload
    def __or__(self, other: UIAction) -> int:
        ...
    @typing.overload
    def __or__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __rand__(self, other: UIAction) -> int:
        ...
    @typing.overload
    def __rand__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    def __repr__(self) -> str:
        ...
    @typing.overload
    def __ror__(self, other: UIAction) -> int:
        ...
    @typing.overload
    def __ror__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __rxor__(self, other: UIAction) -> int:
        ...
    @typing.overload
    def __rxor__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @typing.overload
    def __xor__(self, other: UIAction) -> int:
        ...
    @typing.overload
    def __xor__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class UIMouseButton:
    """
    Members:
    
      MOUSE_BUTTON_1
    
      MOUSE_BUTTON_2
    
      MOUSE_BUTTON_3
    
      MOUSE_BUTTON_4
    
      MOUSE_BUTTON_5
    
      MOUSE_BUTTON_6
    
      MOUSE_BUTTON_7
    
      MOUSE_BUTTON_8
    
      MOUSE_BUTTON_LAST
    
      MOUSE_BUTTON_LEFT
    
      MOUSE_BUTTON_RIGHT
    
      MOUSE_BUTTON_MIDDLE
    """
    MOUSE_BUTTON_1: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_2: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_3: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_4: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_5: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_6: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_7: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_8: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_LAST: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_LEFT: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_MIDDLE: typing.ClassVar[UIMouseButton]
    MOUSE_BUTTON_RIGHT: typing.ClassVar[UIMouseButton]
    __members__: typing.ClassVar[dict[str, UIMouseButton]]
    @typing.overload
    def __and__(self, other: UIMouseButton) -> int:
        ...
    @typing.overload
    def __and__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __eq__(self, other: UIMouseButton) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    @typing.overload
    def __ge__(self, other: UIMouseButton) -> bool:
        ...
    @typing.overload
    def __ge__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    @typing.overload
    def __gt__(self, other: UIMouseButton) -> bool:
        ...
    @typing.overload
    def __gt__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __invert__(self) -> typing.Any:
        ...
    @typing.overload
    def __le__(self, other: UIMouseButton) -> bool:
        ...
    @typing.overload
    def __le__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __lt__(self, other: UIMouseButton) -> bool:
        ...
    @typing.overload
    def __lt__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: UIMouseButton) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    @typing.overload
    def __or__(self, other: UIMouseButton) -> int:
        ...
    @typing.overload
    def __or__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __rand__(self, other: UIMouseButton) -> int:
        ...
    @typing.overload
    def __rand__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    def __repr__(self) -> str:
        ...
    @typing.overload
    def __ror__(self, other: UIMouseButton) -> int:
        ...
    @typing.overload
    def __ror__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __rxor__(self, other: UIMouseButton) -> int:
        ...
    @typing.overload
    def __rxor__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @typing.overload
    def __xor__(self, other: UIMouseButton) -> int:
        ...
    @typing.overload
    def __xor__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class UIKeyEvent:
    """
    Members:
    
      KEY_UNKNOWN
    
      KEY_SPACE
    
      KEY_APOSTROPHE
    
      KEY_COMMA
    
      KEY_MINUS
    
      KEY_PERIOD
    
      KEY_SLASH
    
      KEY_0
    
      KEY_1
    
      KEY_2
    
      KEY_3
    
      KEY_4
    
      KEY_5
    
      KEY_6
    
      KEY_7
    
      KEY_8
    
      KEY_9
    
      KEY_SEMICOLON
    
      KEY_EQUAL
    
      KEY_A
    
      KEY_B
    
      KEY_C
    
      KEY_D
    
      KEY_E
    
      KEY_F
    
      KEY_G
    
      KEY_H
    
      KEY_I
    
      KEY_J
    
      KEY_K
    
      KEY_L
    
      KEY_M
    
      KEY_N
    
      KEY_O
    
      KEY_P
    
      KEY_Q
    
      KEY_R
    
      KEY_S
    
      KEY_T
    
      KEY_U
    
      KEY_V
    
      KEY_W
    
      KEY_X
    
      KEY_Y
    
      KEY_Z
    
      KEY_LEFT_BRACKET
    
      KEY_BACKSLASH
    
      KEY_RIGHT_BRACKET
    
      KEY_GRAVE_ACCENT
    
      KEY_WORLD_1
    
      KEY_WORLD_2
    
      KEY_ESCAPE
    
      KEY_ENTER
    
      KEY_TAB
    
      KEY_BACKSPACE
    
      KEY_INSERT
    
      KEY_DELETE
    
      KEY_RIGHT
    
      KEY_LEFT
    
      KEY_DOWN
    
      KEY_UP
    
      KEY_PAGE_UP
    
      KEY_PAGE_DOWN
    
      KEY_HOME
    
      KEY_END
    
      KEY_CAPS_LOCK
    
      KEY_SCROLL_LOCK
    
      KEY_NUM_LOCK
    
      KEY_PRINT_SCREEN
    
      KEY_PAUSE
    
      KEY_F1
    
      KEY_F2
    
      KEY_F3
    
      KEY_F4
    
      KEY_F5
    
      KEY_F6
    
      KEY_F7
    
      KEY_F8
    
      KEY_F9
    
      KEY_F10
    
      KEY_F11
    
      KEY_F12
    
      KEY_F13
    
      KEY_F14
    
      KEY_F15
    
      KEY_F16
    
      KEY_F17
    
      KEY_F18
    
      KEY_F19
    
      KEY_F20
    
      KEY_F21
    
      KEY_F22
    
      KEY_F23
    
      KEY_F24
    
      KEY_F25
    
      KEY_KP_0
    
      KEY_KP_1
    
      KEY_KP_2
    
      KEY_KP_3
    
      KEY_KP_4
    
      KEY_KP_5
    
      KEY_KP_6
    
      KEY_KP_7
    
      KEY_KP_8
    
      KEY_KP_9
    
      KEY_KP_DECIMAL
    
      KEY_KP_DIVIDE
    
      KEY_KP_MULTIPLY
    
      KEY_KP_SUBTRACT
    
      KEY_KP_ADD
    
      KEY_KP_ENTER
    
      KEY_KP_EQUAL
    
      KEY_LEFT_SHIFT
    
      KEY_LEFT_CONTROL
    
      KEY_LEFT_ALT
    
      KEY_LEFT_SUPER
    
      KEY_RIGHT_SHIFT
    
      KEY_RIGHT_CONTROL
    
      KEY_RIGHT_ALT
    
      KEY_RIGHT_SUPER
    
      KEY_MENU
    
      KEY_LAST
    """
    KEY_0: typing.ClassVar[UIKeyEvent]
    KEY_1: typing.ClassVar[UIKeyEvent]
    KEY_2: typing.ClassVar[UIKeyEvent]
    KEY_3: typing.ClassVar[UIKeyEvent]
    KEY_4: typing.ClassVar[UIKeyEvent]
    KEY_5: typing.ClassVar[UIKeyEvent]
    KEY_6: typing.ClassVar[UIKeyEvent]
    KEY_7: typing.ClassVar[UIKeyEvent]
    KEY_8: typing.ClassVar[UIKeyEvent]
    KEY_9: typing.ClassVar[UIKeyEvent]
    KEY_A: typing.ClassVar[UIKeyEvent]
    KEY_APOSTROPHE: typing.ClassVar[UIKeyEvent]
    KEY_B: typing.ClassVar[UIKeyEvent]
    KEY_BACKSLASH: typing.ClassVar[UIKeyEvent]
    KEY_BACKSPACE: typing.ClassVar[UIKeyEvent]
    KEY_C: typing.ClassVar[UIKeyEvent]
    KEY_CAPS_LOCK: typing.ClassVar[UIKeyEvent]
    KEY_COMMA: typing.ClassVar[UIKeyEvent]
    KEY_D: typing.ClassVar[UIKeyEvent]
    KEY_DELETE: typing.ClassVar[UIKeyEvent]
    KEY_DOWN: typing.ClassVar[UIKeyEvent]
    KEY_E: typing.ClassVar[UIKeyEvent]
    KEY_END: typing.ClassVar[UIKeyEvent]
    KEY_ENTER: typing.ClassVar[UIKeyEvent]
    KEY_EQUAL: typing.ClassVar[UIKeyEvent]
    KEY_ESCAPE: typing.ClassVar[UIKeyEvent]
    KEY_F: typing.ClassVar[UIKeyEvent]
    KEY_F1: typing.ClassVar[UIKeyEvent]
    KEY_F10: typing.ClassVar[UIKeyEvent]
    KEY_F11: typing.ClassVar[UIKeyEvent]
    KEY_F12: typing.ClassVar[UIKeyEvent]
    KEY_F13: typing.ClassVar[UIKeyEvent]
    KEY_F14: typing.ClassVar[UIKeyEvent]
    KEY_F15: typing.ClassVar[UIKeyEvent]
    KEY_F16: typing.ClassVar[UIKeyEvent]
    KEY_F17: typing.ClassVar[UIKeyEvent]
    KEY_F18: typing.ClassVar[UIKeyEvent]
    KEY_F19: typing.ClassVar[UIKeyEvent]
    KEY_F2: typing.ClassVar[UIKeyEvent]
    KEY_F20: typing.ClassVar[UIKeyEvent]
    KEY_F21: typing.ClassVar[UIKeyEvent]
    KEY_F22: typing.ClassVar[UIKeyEvent]
    KEY_F23: typing.ClassVar[UIKeyEvent]
    KEY_F24: typing.ClassVar[UIKeyEvent]
    KEY_F25: typing.ClassVar[UIKeyEvent]
    KEY_F3: typing.ClassVar[UIKeyEvent]
    KEY_F4: typing.ClassVar[UIKeyEvent]
    KEY_F5: typing.ClassVar[UIKeyEvent]
    KEY_F6: typing.ClassVar[UIKeyEvent]
    KEY_F7: typing.ClassVar[UIKeyEvent]
    KEY_F8: typing.ClassVar[UIKeyEvent]
    KEY_F9: typing.ClassVar[UIKeyEvent]
    KEY_G: typing.ClassVar[UIKeyEvent]
    KEY_GRAVE_ACCENT: typing.ClassVar[UIKeyEvent]
    KEY_H: typing.ClassVar[UIKeyEvent]
    KEY_HOME: typing.ClassVar[UIKeyEvent]
    KEY_I: typing.ClassVar[UIKeyEvent]
    KEY_INSERT: typing.ClassVar[UIKeyEvent]
    KEY_J: typing.ClassVar[UIKeyEvent]
    KEY_K: typing.ClassVar[UIKeyEvent]
    KEY_KP_0: typing.ClassVar[UIKeyEvent]
    KEY_KP_1: typing.ClassVar[UIKeyEvent]
    KEY_KP_2: typing.ClassVar[UIKeyEvent]
    KEY_KP_3: typing.ClassVar[UIKeyEvent]
    KEY_KP_4: typing.ClassVar[UIKeyEvent]
    KEY_KP_5: typing.ClassVar[UIKeyEvent]
    KEY_KP_6: typing.ClassVar[UIKeyEvent]
    KEY_KP_7: typing.ClassVar[UIKeyEvent]
    KEY_KP_8: typing.ClassVar[UIKeyEvent]
    KEY_KP_9: typing.ClassVar[UIKeyEvent]
    KEY_KP_ADD: typing.ClassVar[UIKeyEvent]
    KEY_KP_DECIMAL: typing.ClassVar[UIKeyEvent]
    KEY_KP_DIVIDE: typing.ClassVar[UIKeyEvent]
    KEY_KP_ENTER: typing.ClassVar[UIKeyEvent]
    KEY_KP_EQUAL: typing.ClassVar[UIKeyEvent]
    KEY_KP_MULTIPLY: typing.ClassVar[UIKeyEvent]
    KEY_KP_SUBTRACT: typing.ClassVar[UIKeyEvent]
    KEY_L: typing.ClassVar[UIKeyEvent]
    KEY_LAST: typing.ClassVar[UIKeyEvent]
    KEY_LEFT: typing.ClassVar[UIKeyEvent]
    KEY_LEFT_ALT: typing.ClassVar[UIKeyEvent]
    KEY_LEFT_BRACKET: typing.ClassVar[UIKeyEvent]
    KEY_LEFT_CONTROL: typing.ClassVar[UIKeyEvent]
    KEY_LEFT_SHIFT: typing.ClassVar[UIKeyEvent]
    KEY_LEFT_SUPER: typing.ClassVar[UIKeyEvent]
    KEY_M: typing.ClassVar[UIKeyEvent]
    KEY_MENU: typing.ClassVar[UIKeyEvent]
    KEY_MINUS: typing.ClassVar[UIKeyEvent]
    KEY_N: typing.ClassVar[UIKeyEvent]
    KEY_NUM_LOCK: typing.ClassVar[UIKeyEvent]
    KEY_O: typing.ClassVar[UIKeyEvent]
    KEY_P: typing.ClassVar[UIKeyEvent]
    KEY_PAGE_DOWN: typing.ClassVar[UIKeyEvent]
    KEY_PAGE_UP: typing.ClassVar[UIKeyEvent]
    KEY_PAUSE: typing.ClassVar[UIKeyEvent]
    KEY_PERIOD: typing.ClassVar[UIKeyEvent]
    KEY_PRINT_SCREEN: typing.ClassVar[UIKeyEvent]
    KEY_Q: typing.ClassVar[UIKeyEvent]
    KEY_R: typing.ClassVar[UIKeyEvent]
    KEY_RIGHT: typing.ClassVar[UIKeyEvent]
    KEY_RIGHT_ALT: typing.ClassVar[UIKeyEvent]
    KEY_RIGHT_BRACKET: typing.ClassVar[UIKeyEvent]
    KEY_RIGHT_CONTROL: typing.ClassVar[UIKeyEvent]
    KEY_RIGHT_SHIFT: typing.ClassVar[UIKeyEvent]
    KEY_RIGHT_SUPER: typing.ClassVar[UIKeyEvent]
    KEY_S: typing.ClassVar[UIKeyEvent]
    KEY_SCROLL_LOCK: typing.ClassVar[UIKeyEvent]
    KEY_SEMICOLON: typing.ClassVar[UIKeyEvent]
    KEY_SLASH: typing.ClassVar[UIKeyEvent]
    KEY_SPACE: typing.ClassVar[UIKeyEvent]
    KEY_T: typing.ClassVar[UIKeyEvent]
    KEY_TAB: typing.ClassVar[UIKeyEvent]
    KEY_U: typing.ClassVar[UIKeyEvent]
    KEY_UNKNOWN: typing.ClassVar[UIKeyEvent]
    KEY_UP: typing.ClassVar[UIKeyEvent]
    KEY_V: typing.ClassVar[UIKeyEvent]
    KEY_W: typing.ClassVar[UIKeyEvent]
    KEY_WORLD_1: typing.ClassVar[UIKeyEvent]
    KEY_WORLD_2: typing.ClassVar[UIKeyEvent]
    KEY_X: typing.ClassVar[UIKeyEvent]
    KEY_Y: typing.ClassVar[UIKeyEvent]
    KEY_Z: typing.ClassVar[UIKeyEvent]
    __members__: typing.ClassVar[dict[str, UIKeyEvent]]
    @typing.overload
    def __and__(self, other: UIKeyEvent) -> int:
        ...
    @typing.overload
    def __and__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __eq__(self, other: UIKeyEvent) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __eq__(self, other: typing.Any) -> bool:
        ...
    @typing.overload
    def __ge__(self, other: UIKeyEvent) -> bool:
        ...
    @typing.overload
    def __ge__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    @typing.overload
    def __gt__(self, other: UIKeyEvent) -> bool:
        ...
    @typing.overload
    def __gt__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __invert__(self) -> typing.Any:
        ...
    @typing.overload
    def __le__(self, other: UIKeyEvent) -> bool:
        ...
    @typing.overload
    def __le__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __lt__(self, other: UIKeyEvent) -> bool:
        ...
    @typing.overload
    def __lt__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: UIKeyEvent) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.SupportsInt | typing.SupportsIndex) -> bool:
        ...
    @typing.overload
    def __ne__(self, other: typing.Any) -> bool:
        ...
    @typing.overload
    def __or__(self, other: UIKeyEvent) -> int:
        ...
    @typing.overload
    def __or__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __rand__(self, other: UIKeyEvent) -> int:
        ...
    @typing.overload
    def __rand__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    def __repr__(self) -> str:
        ...
    @typing.overload
    def __ror__(self, other: UIKeyEvent) -> int:
        ...
    @typing.overload
    def __ror__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @typing.overload
    def __rxor__(self, other: UIKeyEvent) -> int:
        ...
    @typing.overload
    def __rxor__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    def __setstate__(self, state: typing.SupportsInt | typing.SupportsIndex) -> None:
        ...
    def __str__(self) -> str:
        ...
    @typing.overload
    def __xor__(self, other: UIKeyEvent) -> int:
        ...
    @typing.overload
    def __xor__(self, other: typing.SupportsInt | typing.SupportsIndex) -> int:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class BaseWindow:
    """Base class for displaying images and handling events in a window, deriving from BaseGLFWUI."""
    class RenderMode:
        """
        Members:
        
          GRAY
        
          BGR
        """
        BGR: typing.ClassVar[BaseWindow.RenderMode]
        GRAY: typing.ClassVar[BaseWindow.RenderMode]
        __members__: typing.ClassVar[dict[str, BaseWindow.RenderMode]]
        @typing.overload
        def __eq__(self, other: BaseWindow.RenderMode) -> bool:
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
        def __ne__(self, other: BaseWindow.RenderMode) -> bool:
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
    BGR: typing.ClassVar[BaseWindow.RenderMode]
    GRAY: typing.ClassVar[BaseWindow.RenderMode]
    def get_rendering_mode(self) -> typing.Any:
        """Gets the window’s color rendering mode."""
    def get_size(self) -> tuple[int, int]:
        """
        Returns the tuple (widh, height)
        """
    def poll_events(self) -> None:
        """Dequeues events in this window’s queue and calls corresponding callbacks."""
    def set_close_flag(self) -> None:
        """Asks the window to close."""
    def set_cursor_pos_callback(self, arg0: typing.Any) -> None:
        """Sets a callback that will be called when the mouse’s cursor moves on the current window."""
    def set_keyboard_callback(self, arg0: typing.Any) -> None:
        """Sets a callback that will be called when a key is pressed."""
    def set_mouse_callback(self, arg0: typing.Any) -> None:
        """Sets a callback that will be called when a mouse’s button is pressed."""
    def should_close(self) -> bool:
        """Indicates whether the window has been asked to close."""
class EventLoop:
    """A static class used to dispatch system events to the windows they belong to."""
    @staticmethod
    def poll_and_dispatch(sleep_time_ms: typing.SupportsInt | typing.SupportsIndex = 0) -> None:
        """Polls events from the system and pushes them into the corresponding windows’ internal queue."""
    def __init__(self) -> None:
        ...
class MTWindow(BaseWindow):
    """Window using its own rendering thread to render images."""
    def __enter__(self, *args) -> MTWindow:
        """
        Method that is invoked on entry to the body of the 'with' statement
        """
    def __exit__(self, *args) -> None:
        """
        Method that is invoked on exit from the body of the 'with' statement
        """
    def __init__(self, title: str, width: typing.SupportsInt | typing.SupportsIndex, height: typing.SupportsInt | typing.SupportsIndex, mode: BaseWindow.RenderMode, open_directly: bool = False) -> None:
        ...
    def destroy(self) -> None:
        """
        Destroys the window. This method has to be called after closing the window if this class has been constructed using open_directly=True.
        """
    def show_async(self, image: numpy.ndarray, auto_poll: bool = True) -> None:
        """Asynchronously displays an image."""
class Window(BaseWindow):
    """A window that can be used to display images from any thread."""
    def __enter__(self, *args) -> Window:
        """
        Method that is invoked on entry to the body of the 'with' statement
        """
    def __exit__(self, *args) -> None:
        """
        Method that is invoked on exit from the body of the 'with' statement
        """
    def __init__(self, title: str, width: typing.SupportsInt | typing.SupportsIndex, height: typing.SupportsInt | typing.SupportsIndex, mode: BaseWindow.RenderMode, open_directly: bool = False) -> None:
        ...
    def destroy(self) -> None:
        """
        Destroys the window. This method has to be called after closing the window if this class has been constructed using open_directly=True.
        """
    def show(self, image: numpy.ndarray, auto_poll: bool = True) -> None:
        """Displays an image."""
KEY_0: UIKeyEvent
KEY_1: UIKeyEvent
KEY_2: UIKeyEvent
KEY_3: UIKeyEvent
KEY_4: UIKeyEvent
KEY_5: UIKeyEvent
KEY_6: UIKeyEvent
KEY_7: UIKeyEvent
KEY_8: UIKeyEvent
KEY_9: UIKeyEvent
KEY_A: UIKeyEvent
KEY_APOSTROPHE: UIKeyEvent
KEY_B: UIKeyEvent
KEY_BACKSLASH: UIKeyEvent
KEY_BACKSPACE: UIKeyEvent
KEY_C: UIKeyEvent
KEY_CAPS_LOCK: UIKeyEvent
KEY_COMMA: UIKeyEvent
KEY_D: UIKeyEvent
KEY_DELETE: UIKeyEvent
KEY_DOWN: UIKeyEvent
KEY_E: UIKeyEvent
KEY_END: UIKeyEvent
KEY_ENTER: UIKeyEvent
KEY_EQUAL: UIKeyEvent
KEY_ESCAPE: UIKeyEvent
KEY_F: UIKeyEvent
KEY_F1: UIKeyEvent
KEY_F10: UIKeyEvent
KEY_F11: UIKeyEvent
KEY_F12: UIKeyEvent
KEY_F13: UIKeyEvent
KEY_F14: UIKeyEvent
KEY_F15: UIKeyEvent
KEY_F16: UIKeyEvent
KEY_F17: UIKeyEvent
KEY_F18: UIKeyEvent
KEY_F19: UIKeyEvent
KEY_F2: UIKeyEvent
KEY_F20: UIKeyEvent
KEY_F21: UIKeyEvent
KEY_F22: UIKeyEvent
KEY_F23: UIKeyEvent
KEY_F24: UIKeyEvent
KEY_F25: UIKeyEvent
KEY_F3: UIKeyEvent
KEY_F4: UIKeyEvent
KEY_F5: UIKeyEvent
KEY_F6: UIKeyEvent
KEY_F7: UIKeyEvent
KEY_F8: UIKeyEvent
KEY_F9: UIKeyEvent
KEY_G: UIKeyEvent
KEY_GRAVE_ACCENT: UIKeyEvent
KEY_H: UIKeyEvent
KEY_HOME: UIKeyEvent
KEY_I: UIKeyEvent
KEY_INSERT: UIKeyEvent
KEY_J: UIKeyEvent
KEY_K: UIKeyEvent
KEY_KP_0: UIKeyEvent
KEY_KP_1: UIKeyEvent
KEY_KP_2: UIKeyEvent
KEY_KP_3: UIKeyEvent
KEY_KP_4: UIKeyEvent
KEY_KP_5: UIKeyEvent
KEY_KP_6: UIKeyEvent
KEY_KP_7: UIKeyEvent
KEY_KP_8: UIKeyEvent
KEY_KP_9: UIKeyEvent
KEY_KP_ADD: UIKeyEvent
KEY_KP_DECIMAL: UIKeyEvent
KEY_KP_DIVIDE: UIKeyEvent
KEY_KP_ENTER: UIKeyEvent
KEY_KP_EQUAL: UIKeyEvent
KEY_KP_MULTIPLY: UIKeyEvent
KEY_KP_SUBTRACT: UIKeyEvent
KEY_L: UIKeyEvent
KEY_LAST: UIKeyEvent
KEY_LEFT: UIKeyEvent
KEY_LEFT_ALT: UIKeyEvent
KEY_LEFT_BRACKET: UIKeyEvent
KEY_LEFT_CONTROL: UIKeyEvent
KEY_LEFT_SHIFT: UIKeyEvent
KEY_LEFT_SUPER: UIKeyEvent
KEY_M: UIKeyEvent
KEY_MENU: UIKeyEvent
KEY_MINUS: UIKeyEvent
KEY_N: UIKeyEvent
KEY_NUM_LOCK: UIKeyEvent
KEY_O: UIKeyEvent
KEY_P: UIKeyEvent
KEY_PAGE_DOWN: UIKeyEvent
KEY_PAGE_UP: UIKeyEvent
KEY_PAUSE: UIKeyEvent
KEY_PERIOD: UIKeyEvent
KEY_PRINT_SCREEN: UIKeyEvent
KEY_Q: UIKeyEvent
KEY_R: UIKeyEvent
KEY_RIGHT: UIKeyEvent
KEY_RIGHT_ALT: UIKeyEvent
KEY_RIGHT_BRACKET: UIKeyEvent
KEY_RIGHT_CONTROL: UIKeyEvent
KEY_RIGHT_SHIFT: UIKeyEvent
KEY_RIGHT_SUPER: UIKeyEvent
KEY_S: UIKeyEvent
KEY_SCROLL_LOCK: UIKeyEvent
KEY_SEMICOLON: UIKeyEvent
KEY_SLASH: UIKeyEvent
KEY_SPACE: UIKeyEvent
KEY_T: UIKeyEvent
KEY_TAB: UIKeyEvent
KEY_U: UIKeyEvent
KEY_UNKNOWN: UIKeyEvent
KEY_UP: UIKeyEvent
KEY_V: UIKeyEvent
KEY_W: UIKeyEvent
KEY_WORLD_1: UIKeyEvent
KEY_WORLD_2: UIKeyEvent
KEY_X: UIKeyEvent
KEY_Y: UIKeyEvent
KEY_Z: UIKeyEvent
MOUSE_BUTTON_1: UIMouseButton
MOUSE_BUTTON_2: UIMouseButton
MOUSE_BUTTON_3: UIMouseButton
MOUSE_BUTTON_4: UIMouseButton
MOUSE_BUTTON_5: UIMouseButton
MOUSE_BUTTON_6: UIMouseButton
MOUSE_BUTTON_7: UIMouseButton
MOUSE_BUTTON_8: UIMouseButton
MOUSE_BUTTON_LAST: UIMouseButton
MOUSE_BUTTON_LEFT: UIMouseButton
MOUSE_BUTTON_MIDDLE: UIMouseButton
MOUSE_BUTTON_RIGHT: UIMouseButton
PRESS: UIAction
RELEASE: UIAction
REPEAT: UIAction
