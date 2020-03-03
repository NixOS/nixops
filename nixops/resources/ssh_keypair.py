# -*- coding: utf-8 -*-
from __future__ import annotations

# Automatic provisioning of SSH key pairs.

from typing import Any, Dict, Union, Tuple
import xml.etree.ElementTree as ET

import nixops.deployment
import nixops.resources
import nixops.util


class SSHKeyPairDefinition(nixops.resources.ResourceDefinition):
    """Definition of an SSH key pair."""

    @classmethod
    def get_type(cls) -> str:
        return "ssh-keypair"

    @classmethod
    def get_resource_type(cls) -> str:
        return "sshKeyPairs"

    def __init__(self, xml: ET.Element) -> None:
        nixops.resources.ResourceDefinition.__init__(self, xml)

    def show_type(self) -> str:
        return "{0}".format(self.get_type())


class SSHKeyPairState(nixops.resources.ResourceState):
    """State of an SSH key pair."""

    state = nixops.util.attr_property(
        "state", nixops.resources.ResourceState.MISSING, int
    )
    public_key = nixops.util.attr_property("publicKey", None)
    private_key = nixops.util.attr_property("privateKey", None)

    @classmethod
    def get_type(cls) -> str:
        return "ssh-keypair"

    def __init__(self, depl: nixops.deployment.Deployment, name: str, id: str) -> None:
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def create(
        self,
        defn: nixops.resources.ResourceDefinition,
        check: bool,
        allow_reboot: bool,
        allow_recreate: bool,
    ) -> None:
        # Generate the key pair locally.
        if not self.public_key:
            (private, public) = nixops.util.create_key_pair(type="ed25519")
            with self.depl._db:
                self.public_key = public
                self.private_key = private
                self.state = state = nixops.resources.ResourceState.UP

    def prefix_definition(self, attr: Dict[Any, Any]) -> Dict[Any, Any]:
        return {("resources", "sshKeyPairs"): attr}

    def get_physical_spec(self) -> Dict[Union[Tuple[str, ...], str], Any]:
        return {"privateKey": self.private_key, "publicKey": self.public_key}

    def destroy(self, wipe: bool = False) -> bool:
        return True
