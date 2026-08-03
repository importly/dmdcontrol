from typing import ClassVar

class Font():
   """
   Provides escape codes for text formatting.
   """
   # Reset
   ENDC: ClassVar[str] = '\033[0m'
   
   # Text styles
   BOLD: ClassVar[str] = '\033[1m'
   DIM: ClassVar[str] = '\033[2m'
   ITALIC: ClassVar[str] = '\033[3m'
   UNDERLINE: ClassVar[str] = '\033[4m' 
   INVERSE: ClassVar[str] = '\033[7m'
   STRIKE: ClassVar[str] = '\033[9m'
   DOUBLE_UNDERLINE: ClassVar[str] = '\033[21m'
   
   # Colors
   BLACK: ClassVar[str] = '\033[30m'
   RED: ClassVar[str] = '\033[31m'
   GREEN: ClassVar[str] = '\033[32m'
   YELLOW: ClassVar[str] = '\033[33m'
   BLUE: ClassVar[str] = '\033[34m'
   PURPLE: ClassVar[str] = '\033[35m'
   TEAL: ClassVar[str] = '\033[36m'
   WHITE: ClassVar[str] = '\033[37m'
   
   # Background colors
   BG_BLACK: ClassVar[str] = '\033[40m'
   BG_RED: ClassVar[str] = '\033[41m'
   BG_GREEN: ClassVar[str] = '\033[42m'
   BG_YELLOW: ClassVar[str] = '\033[43m'
   BG_BLUE: ClassVar[str] = '\033[44m'
   BG_PURPLE: ClassVar[str] = '\033[45m'
   BG_TEAL: ClassVar[str] = '\033[46m'
   BG_WHITE: ClassVar[str] = '\033[47m'
   
   # Helpers
   VERBOSE: ClassVar[str] = f'{BOLD + PURPLE}[VERBOSE]{ENDC}'
