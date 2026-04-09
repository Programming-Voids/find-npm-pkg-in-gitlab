"""
Utility functions, data classes, and logging setup for the GitLab package scanner.
"""

import logging
import sys
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional

from tqdm import tqdm

from .config import (
    ANSI_BOLD,
    ANSI_BLUE,
    ANSI_CYAN,
    ANSI_DIM,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_RED,
    ANSI_RESET,
    ANSI_YELLOW,
    PRINT_LOCK,
)


@dataclass
class MatchRule:
    packages: List[str]
    exact_versions: List[str]
    version_ranges: List[str]


@dataclass
class RunStats:
    started_at: float
    repos_completed: int = 0
    repos_with_findings: int = 0
    branches_checked: int = 0
    files_checked: int = 0
    matches_found: int = 0
    errors_seen: int = 0


STATS_LOCK = Lock()
RUN_STATS = RunStats(started_at=time.time())


def update_stats(
    repos_completed: int = 0,
    repos_with_findings: int = 0,
    branches_checked: int = 0,
    files_checked: int = 0,
    matches_found: int = 0,
    errors_seen: int = 0,
) -> None:
    """Thread-safely update the global run statistics."""
    with STATS_LOCK:
        RUN_STATS.repos_completed += repos_completed
        RUN_STATS.repos_with_findings += repos_with_findings
        RUN_STATS.branches_checked += branches_checked
        RUN_STATS.files_checked += files_checked
        RUN_STATS.matches_found += matches_found
        RUN_STATS.errors_seen += errors_seen


def get_stats_snapshot() -> RunStats:
    """Thread-safely get a snapshot of the current run statistics."""
    with STATS_LOCK:
        return RunStats(
            started_at=RUN_STATS.started_at,
            repos_completed=RUN_STATS.repos_completed,
            repos_with_findings=RUN_STATS.repos_with_findings,
            branches_checked=RUN_STATS.branches_checked,
            files_checked=RUN_STATS.files_checked,
            matches_found=RUN_STATS.matches_found,
            errors_seen=RUN_STATS.errors_seen,
        )


def format_live_summary(total_projects: int) -> str:
    """Format a live summary string for the progress bar showing current stats and throughput."""
    stats = get_stats_snapshot()
    # Avoid division by zero by ensuring minimum elapsed time
    elapsed = max(time.time() - stats.started_at, 0.001)

    # Calculate throughput rates (items per second)
    repo_rate = stats.repos_completed / elapsed
    branch_rate = stats.branches_checked / elapsed
    file_rate = stats.files_checked / elapsed

    # Format as compact status string for progress bar
    return (
        f"done={stats.repos_completed}/{total_projects} "      # Progress: completed/total
        f"findings={stats.repos_with_findings} "               # Repos with matches found
        f"matches={stats.matches_found} "                      # Total package matches
        f"errors={stats.errors_seen} "                         # Errors encountered
        f"repo/s={repo_rate:.2f} "                              # Repository scan rate
        f"branch/s={branch_rate:.2f} "                          # Branch scan rate
        f"file/s={file_rate:.2f}"                               # File scan rate
    )


class TqdmLoggingHandler(logging.Handler):
    """Custom logging handler that writes to tqdm progress bar.

    This handler ensures that log messages don't interfere with the progress bar
    display by using tqdm's write() method instead of direct stdout writes.
    Thread-safe output is ensured using PRINT_LOCK.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to stderr through tqdm for progress bar compatibility.
        
        Uses tqdm.write() which automatically handles line breaks and progress bar
        repositioning to keep output readable.
        """
        try:
            msg = self.format(record)
            # Use tqdm.write() to avoid interfering with progress bar display
            # PRINT_LOCK ensures thread-safe output from multiple worker threads
            with PRINT_LOCK:
                tqdm.write(msg, file=sys.stderr)
        except Exception:
            # Handle any formatting or output errors gracefully
            self.handleError(record)


class ColorConsoleFormatter(logging.Formatter):
    """Logging formatter that adds ANSI color codes to log levels."""

    LEVEL_COLORS = {
        logging.DEBUG: ANSI_DIM,
        logging.INFO: ANSI_CYAN,
        logging.WARNING: ANSI_YELLOW,
        logging.ERROR: ANSI_RED,
        logging.CRITICAL: ANSI_RED + ANSI_RESET + ANSI_BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with colorized level and timestamp."""
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = record.levelname
        message = record.getMessage()
        from .config import USE_COLOR, colorize
        if USE_COLOR:
            ts = colorize(ts, ANSI_DIM)
            level = colorize(level, self.LEVEL_COLORS.get(record.levelno, ""))
        return f"{ts} | {level} | {message}"


LOGGER = logging.getLogger("gitlab_file_scanner")


def setup_logging(log_file: str, verbose: bool) -> None:
    """Set up logging with file and console handlers.
    
    Creates two logging outputs:
    1. File handler: Detailed logs with timestamps and thread names
    2. Console handler: Shorter format optimized for terminal display with colors
    
    The console handler uses TqdmLoggingHandler to integrate with progress bars.
    """
    level = logging.DEBUG if verbose else logging.INFO
    LOGGER.setLevel(level)
    LOGGER.handlers.clear()
    LOGGER.propagate = False

    # File handler: Full detailed logs with formatting for log analysis
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Console handler: Shorter format with colors, compatible with progress bar
    console_handler = TqdmLoggingHandler()
    console_handler.setLevel(level if verbose else logging.INFO)
    console_handler.setFormatter(ColorConsoleFormatter())

    # Attach both handlers to the logger
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(console_handler)


def log_terminal_line(message: str, color: Optional[str] = None) -> None:
    """Log a message to the terminal with optional color, thread-safely.
    
    This is used for high-level status updates that should appear immediately
    in the terminal. Uses tqdm.write() for progress bar compatibility.
    """
    from .config import colorize
    # Apply color if specified (can be disabled via NO_COLOR env var)
    if color:
        message = colorize(message, color)
    # Write to stderr with thread-safe locking
    with PRINT_LOCK:
        tqdm.write(message, file=sys.stderr)


def fail(msg: str, code: int = 1) -> None:
    """Log an error message and exit the program with the given code.
    
    Used for startup validation failures (e.g., missing environment variables).
    Logs both to the logger and stderr to ensure the message is visible.
    """
    LOGGER.error(msg)
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def normalize_list(values: List[str]) -> List[str]:
    """Normalize a list of strings by stripping whitespace and removing duplicates while preserving order.

    This function:
    - Strips leading/trailing whitespace from each value
    - Filters out empty strings after stripping
    - Removes duplicates while maintaining original order
    - Returns a clean, deduplicated list
    """
    out: List[str] = []
    seen = set()
    for value in values:
        # Strip whitespace and skip empty values
        v = value.strip()
        if not v:
            continue
        # Skip duplicates
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out
