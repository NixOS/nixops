from nixops.util import ImmutableValidatedObject
from . import LockDriver


class NoopLockOptions(ImmutableValidatedObject):
    pass


class NoopLock(LockDriver[NoopLockOptions]):
    __options = NoopLockOptions

    @staticmethod
    def options(**kwargs) -> NoopLockOptions:
        return NoopLockOptions(**kwargs)

    def __init__(self, args: NoopLockOptions) -> None:
        pass

    def unlock(self, **_kwargs) -> None:
        pass

    def lock(self, **_kwargs) -> None:
        pass
