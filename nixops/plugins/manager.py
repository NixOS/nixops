from __future__ import annotations

from nixops.backends import MachineState
from typing import List, Dict, Generator, Tuple, Any, Set
import importlib

from nixops.storage import StorageBackend
from nixops.locks import LockDriver
from . import get_plugins, MachineHooks, DeploymentHooks
import nixops.ansi
import nixops
from typing import Type
import sys


NixosConfigurationType = List[Dict[Tuple[str, ...], Any]]


class DeploymentHooksManager:
    @staticmethod
    def physical_spec(
        deployment: "nixops.deployment.Deployment",
    ) -> Dict[str, NixosConfigurationType]:
        attrs_per_resource: Dict[str, NixosConfigurationType] = {}

        for hook in PluginManager.deployment_hooks():
            for name, attrs in hook.physical_spec(deployment).items():
                if name not in attrs_per_resource:
                    attrs_per_resource[name] = []
                attrs_per_resource[name].extend(attrs)

        return attrs_per_resource


class MachineHooksManager:
    @staticmethod
    def post_wait(m: MachineState) -> None:
        for hook in PluginManager.machine_hooks():
            hook.post_wait(m)


class PluginManager:
    @staticmethod
    def deployment_hooks() -> Generator[DeploymentHooks, None, None]:
        for plugin in get_plugins():
            machine_hooks = plugin.deployment_hooks()
            if not machine_hooks:
                continue
            yield machine_hooks

    @staticmethod
    def machine_hooks() -> Generator[MachineHooks, None, None]:
        for plugin in get_plugins():
            machine_hooks = plugin.machine_hooks()
            if not machine_hooks:
                continue
            yield machine_hooks

    @classmethod
    def load(cls):
        seen: Set[str] = set()
        for plugin in get_plugins():
            for mod in plugin.load():
                if mod not in seen:
                    importlib.import_module(mod)
                seen.add(mod)

    @staticmethod
    def nixexprs() -> List[str]:
        nixexprs: List[str] = []
        for plugin in get_plugins():
            nixexprs.extend(plugin.nixexprs())
        return nixexprs

    @staticmethod
    def parser(parser, subparsers):
        for plugin in get_plugins():
            plugin.parser(parser, subparsers)

    @staticmethod
    def docs() -> Generator[Tuple[str, str], None, None]:
        for plugin in get_plugins():
            yield from plugin.docs()

    @staticmethod
    def storage_backends() -> Dict[str, Type[StorageBackend]]:
        storage_backends: Dict[str, Type[StorageBackend]] = {}

        for plugin in get_plugins():
            for name, backend in plugin.storage_backends().items():
                if name not in storage_backends:
                    storage_backends[name] = backend
                else:
                    sys.stderr.write(
                        nixops.ansi.ansi_warn(
                            f"Two plugins tried to provide the '{name}' storage backend."
                        )
                    )

        return storage_backends

    @staticmethod
    def lock_drivers() -> Dict[str, Type[LockDriver]]:
        lock_drivers: Dict[str, Type[LockDriver]] = {}

        for plugin in get_plugins():
            for name, driver in plugin.lock_drivers().items():
                if name not in lock_drivers:
                    lock_drivers[name] = driver
                else:
                    sys.stderr.write(
                        nixops.ansi.ansi_warn(
                            f"Two plugins tried to provide the '{name}' lock driver."
                        )
                    )

        return lock_drivers
