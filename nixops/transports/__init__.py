from .exceptions import ConnectionFailed, CommandFailed
from typing_extensions import Protocol
from typing import Iterable
import nixops.util


__all__ = (
    "ConnectionFailed",
    "CommandFailed",
    "Transport",
)


class Transport(Protocol):

    def __init__(self, machine):
        pass

    def reset(self) -> None:
        pass

    def upload_file(self, source: str, target: str, recursive: bool = False) -> None:
        pass

    def download_file(self, source: str, target: str, recursive: bool = False) -> None:
        pass

    def run_command(
        self, command: Iterable[str], **kwargs
    ) -> nixops.util.ProcessResult:
        pass

    def copy_closure(self, path: str):
        pass
