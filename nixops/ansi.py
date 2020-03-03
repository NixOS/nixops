import sys
from typing import TextIO


def ansi_highlight(s: str, outfile: TextIO = sys.stderr) -> str:
    return "\033[1;35m" + s + "\033[0m" if outfile.isatty() else s


def ansi_warn(s: str, outfile: TextIO = sys.stderr) -> str:
    return "\033[1;33m" + s + "\033[0m" if outfile.isatty() else s


def ansi_error(s: str, outfile: TextIO = sys.stderr) -> str:
    return "\033[1;31m" + s + "\033[0m" if outfile.isatty() else s


def ansi_success(s: str, outfile: TextIO = sys.stderr) -> str:
    return "\033[1;32m" + s + "\033[0m" if outfile.isatty() else s
