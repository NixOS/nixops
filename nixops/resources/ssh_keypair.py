from __future__ import annotations

# Automatic provisioning of SSH key pairs.
from typing import Type, Dict, Optional

from nixops.state import RecordId
import nixops.util
import nixops.resources


class SSHKeyPairDefinition(nixops.resources.ResourceDefinition):
    """Definition of an SSH key pair."""

    config: nixops.resources.ResourceOptions

    @classmethod
    def get_type(cls: Type[SSHKeyPairDefinition]) -> str:
        return "ssh-keypair"

    @classmethod
    def get_resource_type(cls: Type[SSHKeyPairDefinition]) -> str:
        return "sshKeyPairs"

    def __init__(self, name: str, config: nixops.resources.ResourceEval):
        super().__init__(name, config)

    def show_type(self) -> str:
        return "{0}".format(self.get_type())


class SSHKeyPairState(nixops.resources.ResourceState[SSHKeyPairDefinition]):
    """State of an SSH key pair."""

    state = nixops.util.attr_property(
        "state", nixops.resources.ResourceState.MISSING, int
    )
    public_key: Optional[str] = nixops.util.attr_property("publicKey", None)
    private_key: Optional[str] = nixops.util.attr_property("privateKey", None)

    @classmethod
    def get_type(cls: Type[SSHKeyPairState]) -> str:
        return "ssh-keypair"

    def __init__(self, depl: "nixops.deployment.Deployment", name: str, id: RecordId):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def create(
        self,
        defn: SSHKeyPairDefinition,
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
                self.state = nixops.resources.ResourceState.UP

    def prefix_definition(self, attr) -> Dict:
        return {("resources", "sshKeyPairs"): attr}

    def get_physical_spec(self) -> Dict[str, Optional[str]]:
        return {"privateKey": self.private_key, "publicKey": self.public_key}

    def destroy(self, wipe: bool = False) -> bool:
        return True
