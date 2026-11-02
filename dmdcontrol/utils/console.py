"""The run's rich console. Log lines and progress bars share it, so logs scroll above a pinned bar."""

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

CONSOLE = Console()


def progress_bar(download: bool = False, refresh_per_second: float = 10) -> Progress:
    """A uv-style bar on CONSOLE: done/total, elapsed and ETA, or bytes and speed for a download."""
    amount = (DownloadColumn(), TransferSpeedColumn()) if download else (MofNCompleteColumn(), TimeElapsedColumn())
    return Progress(
        TextColumn('[bold]{task.description}'),
        BarColumn(bar_width=None),
        *amount,
        TextColumn('eta'),
        TimeRemainingColumn(),
        console=CONSOLE,
        refresh_per_second=refresh_per_second,
    )
