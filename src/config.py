#!/usr/bin/env python3
"""
Configuration constants and setup for the GitLab package scanner.
"""

import os
import requests
from threading import Lock
from urllib.parse import quote

# GitLab API configuration loaded from environment variables
GITLAB_URL = os.environ.get("GITLAB_URL", "").rstrip("/")  # GitLab instance URL
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")  # Personal/group access token for API authentication

# Request timeout for GitLab API calls (in seconds)
REQUEST_TIMEOUT = 30  # Default timeout in seconds

# Session object with GitLab authentication headers pre-configured
# Reused across all API requests to maintain connection pooling and improve performance
SESSION = requests.Session()
SESSION.headers.update({"PRIVATE-TOKEN": GITLAB_TOKEN})

# Thread-safe lock for coordinating printer output from multiple worker threads
# Prevents garbled output when multiple threads try to print simultaneously
PRINT_LOCK = Lock()

# ANSI color codes for terminal output (can be disabled with NO_COLOR env var)
ANSI_RESET = "\033[0m"  # Reset to default terminal color
ANSI_BOLD = "\033[1m"  # Bold text
ANSI_DIM = "\033[2m"  # Dimmed/faded text
ANSI_RED = "\033[31m"  # Red text (errors)
ANSI_GREEN = "\033[32m"  # Green text (successes/matches)
ANSI_YELLOW = "\033[33m"  # Yellow text (warnings)
ANSI_BLUE = "\033[34m"  # Blue text (info/starting)
ANSI_CYAN = "\033[36m"  # Cyan text (configuration)
ANSI_MAGENTA = "\033[35m"  # Magenta text (branch/branch-level info)


def supports_color() -> bool:
    """Check if the terminal supports color output based on NO_COLOR environment variable and tty detection."""
    if os.environ.get("NO_COLOR"):
        return False
    import sys
    return sys.stderr.isatty()


USE_COLOR = supports_color()


def colorize(text: str, color: str) -> str:
    """Apply ANSI color codes to text if color output is supported."""
    if not USE_COLOR:
        return text
    return f"{color}{text}{ANSI_RESET}"
