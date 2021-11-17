from __future__ import annotations

from nixops.backends import GenericMachineState
from typing import List, Dict, Optional, Union, Tuple, Type
from argparse import ArgumentParser, _SubParsersAction

from nixops.storage import StorageBackend
from nixops.locks import LockDriver
from typing import Generator
import pluggy # type: ignore
import nixops


hookimpl = pluggy.HookimplMarker("nixops")
"""Marker to be imported and used in plugins (and for own implementations)"""


def get_plugin_manager() -> pluggy.PluginManager:
    from . import hookspecs

    pm = pluggy.PluginManager("nixops")
    pm.add_hookspecs(hookspecs)
    pm.load_setuptools_entrypoints("nixops")
    return pm


def get_plugins() -> Generator[Plugin, None, None]:
    pm = get_plugin_manager()
    for plugin in pm.hook.plugin():
        yield plugin


class DeploymentHooks:
    """
    Deployment level hooks
    """

    def physical_spec(
        self, d: "nixops.deployment.Deployment"
    ) -> Dict[str, Union[List[Dict], Dict]]:
        """
        Manipulate NixOS configurations for machines in deployment

        :return a dict with NixOS configuration
        """
        return {}


class MachineHooks:
    def post_wait(self, m: GenericMachineState) -> None:
        """
        Do action once SSH is available
        """
        pass


class Plugin:
    def deployment_hooks(self) -> Optional[DeploymentHooks]:
        """
        Run deployment hooks
        """
        return None

    def machine_hooks(self) -> Optional[MachineHooks]:
        """
        Run machine hooks
        """
        return None

    def load(self) -> List[str]:
        """
        Load plugins (import)

        :return a list of modules to import
        """
        return []

    def nixexprs(self) -> List[str]:
        """
        Get all the Nix expressions to load

        :return a list of Nix expressions to import
        """
        return []

    def parser(self, parser: ArgumentParser, subparsers: _SubParsersAction) -> None:
        """
        Extend the core nixops cli parser
        """
        pass

    def docs(self) -> List[Tuple[str, str]]:
        """ Extend docs
        :return a list of tuples (plugin_name, doc_path)
        """
        return []

    def lock_drivers(self) -> Dict[str, Type[LockDriver]]:
        return {}

    def storage_backends(self) -> Dict[str, Type[StorageBackend]]:
        """ Extend the core nixops cli parser
        :return a set of plugin parser extensions
        """
        return {}
