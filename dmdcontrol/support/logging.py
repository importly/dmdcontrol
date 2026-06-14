import logging

from rich.console import Console
from rich.logging import RichHandler

# Create a global rich console for direct printing if needed
console = Console()


def setup_logger(verbosity=0, verbose=None):
    """
    Configure the root logger with rich formatting.

    Args:
        verbosity: 0 = basic INFO, 1 = DEBUG, 2+ = DEBUG with source paths.
    """
    if verbose is not None:
        verbosity = verbose
    if isinstance(verbosity, bool):
        verbosity = 1 if verbosity else 0
    level = logging.DEBUG if verbosity >= 1 else logging.INFO
    # Configure logging
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True,
                              show_path=verbosity >= 2,
                              console=console)],
        force=True,
    )

    logger = logging.getLogger("dmdcontrol")
    logger.setLevel(level)
    return logger


# Create a default logger instance
logger = logging.getLogger("dmdcontrol")
