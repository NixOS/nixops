import pluggy
from nixops.storage import BackendRegistration

hookspec = pluggy.HookspecMarker("nixops")


@hookspec
def load():
    """ Load plugins (import)
    :return a list of modules to import
    """


@hookspec
def nixexprs():
    """ Get all the Nix expressions to load
    :return a list of Nix expressions to import
    """


@hookspec
def parser(parser, subparsers):
    """ Extend the core nixops cli parser
    :return a set of plugin parser extensions
    """


@hookspec
def register_backends() -> BackendRegistration:
    """ Extend the core nixops cli parser
    :return a set of plugin parser extensions
    """
