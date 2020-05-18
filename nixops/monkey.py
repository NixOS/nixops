from typing import TYPE_CHECKING

__all__ = (
    "Protocol",
    "runtime_checkable",
)

# ☢️☢️☢️☢️☢️☢️☢️ 2020-05-18 ☢️☢️☢️☢️☢️☢️☢️
# Explicitly subclassed Protocols don't support super().__init__
#
# ... but we need that.
#
# See: https://github.com/python/typing/issues/572 for a description, including
# the below workaround.
#
# Protocol doesn't give us any special run-time behavior (except for
# runtime_checkable,) and can be pretty transparently swapped out for
# Generic at run time.
#
# By using Generic at run-time, we get the expected __init__ behavior.
#
# But, we still want Protocols at type-checking time because Protocol
# is much stricter about assigning to `self` without explicitly defining
# and typing the object variable.
#
# In conclusion, I'm sorry. Hopefully #572 gets fixed and we can delete
# this and go back to the isinstance check in deployment.py.

if not TYPE_CHECKING:
    from typing import Generic

    Protocol = Generic

    def runtime_checkable(f):
        return f


else:
    from typing_extensions import Protocol, runtime_checkable
