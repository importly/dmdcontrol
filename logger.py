import logging
import sys
from rich.logging import RichHandler
from rich.console import Console

# Create a global rich console for direct printing if needed
console = Console()


def setup_logger(verbose=False):
    """
    Configure the root logger with rich formatting.

    Args:
        verbose (bool): If True, sets level to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO

    # Configure logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(rich_tracebacks=True, show_path=verbose, console=console)
        ],
    )

    logger = logging.getLogger("dmdcontrol")
    logger.setLevel(level)
    return logger


# Create a default logger instance
logger = logging.getLogger("dmdcontrol")
