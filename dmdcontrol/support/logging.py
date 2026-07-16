import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from rich.console import Console
from rich.logging import RichHandler

# Create a global rich console for direct printing if needed
console = Console()
_log_context_label: ContextVar[str | None] = ContextVar(
    "dmdcontrol_log_context_label",
    default=None,
)


class _ContextLabelFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        label = _log_context_label.get()
        if label is None or getattr(record, "_dmdcontrol_context_label", None) is not None:
            return True

        record.msg = f"[{label}] {record.getMessage()}"
        record.args = ()
        record._dmdcontrol_context_label = label
        return True


@contextmanager
def log_context(label: str) -> Iterator[None]:
    """Prefix dmdcontrol log records in this execution context with ``label``."""
    token = _log_context_label.set(label)
    try:
        yield
    finally:
        _log_context_label.reset(token)


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

    logger.setLevel(level)
    return logger


# Create a default logger instance
logger = logging.getLogger("dmdcontrol")
logger.addFilter(_ContextLabelFilter())
