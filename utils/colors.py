# utils/colors.py

import sys
import os


def _supports_ansi() -> bool:
    """
    Returns True if the terminal supports ANSI colors.
    Windows before Win10 often does not, so we disable colors there.
    """
    if sys.platform != "win32":
        return True

    # Windows terminals that support ANSI (Win10+, new PowerShell)
    return os.environ.get("ANSICON") is not None or \
           os.environ.get("WT_SESSION") is not None or \
           "TERM" in os.environ


ANSI_ENABLED = _supports_ansi()


class Color:
    """Simple ANSI color helper for clean and readable console output."""

    if ANSI_ENABLED:
        YELLOW = "\033[93m"
        GREEN = "\033[92m"
        RED = "\033[91m"
        BLUE = "\033[94m"
        MAGENTA = "\033[95m"
        CYAN = "\033[96m"
        WHITE = "\033[97m"
        BOLD = "\033[1m"
        RESET = "\033[0m"
    else:
        # No color support → empty strings
        YELLOW = ""
        GREEN = ""
        RED = ""
        BLUE = ""
        MAGENTA = ""
        CYAN = ""
        WHITE = ""
        BOLD = ""
        RESET = ""
