from . import Plugin

import pluggy  # type: ignore


hookspec = pluggy.HookspecMarker("nixops")


@hookspec
def plugin() -> Plugin:
    """
    Register a plugin base class
    """
