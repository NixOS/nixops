from __future__ import annotations
from typing import Mapping, Any, Type, TypeVar, TYPE_CHECKING

from typing_extensions import Protocol

if TYPE_CHECKING:
    import nixops.statefile


T = TypeVar("T")
StorageArgValues = Mapping[str, Any]


class StorageBackend(Protocol[T]):
    # Hack: Make T a mypy invariant. According to PEP-0544, a
    # Protocol[T] whose T is only used in function arguments and
    # returns is "de-facto covariant".
    #
    # However, a Protocol[T] which requires an attribute of type T is
    # invariant, "since it has a mutable attribute".
    #
    # I don't really get it, to be honest. That said, since it is
    # defined by the type, please set it ... even though mypy doesn't
    # force you to. What even.
    #
    # See: https://www.python.org/dev/peps/pep-0544/#generic-protocols
    __options: Type[T]

    @staticmethod
    def options(**kwargs) -> T:
        pass

    def __init__(self, args: T) -> None:
        raise NotImplementedError

    # fetchToFile: download the state file to the local disk.
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def fetchToFile(self, path: str, **kwargs) -> None:
        raise NotImplementedError

    # onOpen: receive the StateFile object for last-minute, backend
    # specific changes to the state file.
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def onOpen(self, sf: nixops.statefile.StateFile, **kwargs) -> None:
        pass

    # uploadFromFile: upload the new version of the state file
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def uploadFromFile(self, path: str, **kwargs) -> None:
        raise NotImplementedError
