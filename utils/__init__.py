"""
tn-bench Utilities
Common utilities for formatting, colors, and helper functions.
"""

import sys

# ANSI color codes
COLORS = {
    "HEADER": "\033[95m",
    "BLUE": "\033[94m",
    "CYAN": "\033[96m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "RED": "\033[91m",
    "BOLD": "\033[1m",
    "UNDERLINE": "\033[4m",
    "ENDC": "\033[0m",
}


def color_text(text, color_name):
    """Apply color to text if output is a terminal"""
    if sys.stdout.isatty() and color_name in COLORS:
        return f"{COLORS[color_name]}{text}{COLORS['ENDC']}"
    return text


def print_header(title):
    """Print a formatted header with separators"""
    separator = "#" * 60
    print()
    print(color_text(separator, "BLUE"))
    print(color_text(f"# {title.center(56)} #", "BOLD"))
    print(color_text(separator, "BLUE"))
    print()


def print_subheader(title):
    """Print a subheader with separators"""
    separator = "-" * 60
    print()
    print(color_text(separator, "CYAN"))
    print(color_text(f"| {title.center(56)} |", "BOLD"))
    print(color_text(separator, "CYAN"))
    print()


def print_section(title):
    """Print a section separator"""
    separator = "=" * 60
    print()
    print(color_text(separator, "GREEN"))
    print(color_text(f" {title} ", "BOLD"))
    print(color_text(separator, "GREEN"))
    print()


def print_warning(message):
    """Print a warning message"""
    print(color_text(f"! WARNING: {message}", "YELLOW"))


def print_error(message):
    """Print an error message"""
    print(color_text(f"! ERROR: {message}", "RED"))


def print_info(message):
    """Print an informational message"""
    print(color_text(f"* {message}", "CYAN"))


def print_success(message):
    """Print a success message"""
    print(color_text(f"✓ {message}", "GREEN"))


def print_bullet(message):
    """Print a bullet point"""
    print(color_text(f"• {message}", "ENDC"))
