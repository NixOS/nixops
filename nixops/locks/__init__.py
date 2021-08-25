from typing import TypeVar, Type
from typing_extensions import Protocol


"""
Interface to a lock driver.

An implementation should inherit from LockDriver in order to for a plugin to be
able to integrate it.
"""


# This separation was introduced to hide the LockOptions details from the
# LockInterface type. It only matters for construction and clients don't have
# to know about it.
class LockInterface(Protocol):
    # lock: acquire a lock.
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def lock(self, **kwargs) -> None:
        raise NotImplementedError

    # unlock: release the lock.
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def unlock(self, **kwargs) -> None:
        raise NotImplementedError


LockOptions = TypeVar("LockOptions")


class LockDriver(LockInterface, Protocol[LockOptions]):
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
    __options: Type[LockOptions]

    @staticmethod
    def options(**kwargs) -> LockOptions:
        pass

    def __init__(self, args: LockOptions) -> None:
        raise NotImplementedError
