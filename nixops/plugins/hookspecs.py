from typing import List, Dict, Optional
from nixops.backends import MachineState

import pluggy


hookspec = pluggy.HookspecMarker("nixops")


class DeploymentHooks:
    """
    Deployment level hooks
    """

    def physical_spec(self, d) -> Dict[str, Dict]:
        """
        Manipulate NixOS configurations for machines in deployment

        :return a dict with NixOS configuration
        """
        return {}


class MachineHooks:
    def post_wait(self, m: MachineState) -> None:
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

    def parser(self, parser, subparsers):
        """
        Extend the core nixops cli parser
        """
        pass


@hookspec
def plugin() -> Plugin:
    """
    Register a plugin base class
    """
    pass
