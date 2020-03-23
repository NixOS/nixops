from . import Plugin

import pluggy


hookspec = pluggy.HookspecMarker("nixops")


@hookspec
def plugin() -> Plugin:
    """
    Register a plugin base class
    """
