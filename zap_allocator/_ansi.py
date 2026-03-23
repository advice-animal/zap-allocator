"""ANSI escape codes and display thresholds."""

from __future__ import annotations

_RED = "\033[31m"
_GRN = "\033[32m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RST = "\033[0m"
_CLR = "\033[2J\033[H"  # clear screen + home cursor

_LARGE_DELTA = 1_000  # blocks; changes this big get bold emphasis
