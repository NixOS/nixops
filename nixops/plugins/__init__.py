from functools import lru_cache
from typing import Generator
import pluggy
from . import hookspecs

hookimpl = pluggy.HookimplMarker("nixops")
"""Marker to be imported and used in plugins (and for own implementations)"""


@lru_cache()
def get_plugin_manager():
    pm = pluggy.PluginManager("nixops")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("nixops")
    return pm


def get_plugins() -> Generator[hookspecs.Plugin, None, None]:
    pm = get_plugin_manager()
    for plugin in pm.hook.plugin():
        yield plugin
