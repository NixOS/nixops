import pluggy
from . import hookspecs

hookimpl = pluggy.HookimplMarker("nixops")
"""Marker to be imported and used in plugins (and for own implementations)"""


def get_plugin_manager():
    pm = pluggy.PluginManager("nixops")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("nixops")
    return pm
