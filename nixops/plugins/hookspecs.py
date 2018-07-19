import pluggy


hookspec = pluggy.HookspecMarker("nixops")


@hookspec
def load():
    """Load plugins (import)
    :return a list of modules to import
    """
