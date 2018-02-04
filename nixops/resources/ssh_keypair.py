# -*- coding: utf-8 -*-

# Automatic provisioning of SSH key pairs.

import nixops.util
import nixops.resources


class SSHKeyPairDefinition(nixops.resources.ResourceDefinition):
    """Definition of an SSH key pair."""

    @classmethod
    def get_type(cls):
        return "ssh-keypair"

    @classmethod
    def get_resource_type(cls):
        return "sshKeyPairs"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)

    def show_type(self):
        return "{0}".format(self.get_type())


class SSHKeyPairState(nixops.resources.ResourceState):
    """State of an SSH key pair."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    public_key = nixops.util.attr_property("publicKey", None)
    private_key = nixops.util.attr_property("privateKey", None)


    @classmethod
    def get_type(cls):
        return "ssh-keypair"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


    def create(self, defn, check, allow_reboot, allow_recreate):
        # Generate the key pair locally.
        if not self.public_key:
            (private, public) = nixops.util.create_key_pair(type="ed25519")
            with self.depl._state.db:
                self.public_key = public
                self.private_key = private
                self.state = state = nixops.resources.ResourceState.UP

    def prefix_definition(self, attr):
        return {('resources', 'sshKeyPairs'): attr}

    def get_physical_spec(self):
        return {'privateKey': self.private_key,
                'publicKey': self.public_key}

    def destroy(self, wipe=False):
        return True
