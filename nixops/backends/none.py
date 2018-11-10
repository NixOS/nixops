# -*- coding: utf-8 -*-
import os
import sys
import nixops.util

from nixops.backends import MachineDefinition, MachineState
from nixops.util import attr_property, create_key_pair


class NoneDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        self._target_host = xml.find("attrs/attr[@name='targetHost']/string").get("value")

        public_ipv4 = xml.find("attrs/attr[@name='publicIPv4']/string")
        self._public_ipv4 = None if public_ipv4 is None else public_ipv4.get("value")

class NoneState(MachineState):
    """State of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"

    target_host = nixops.util.attr_property("targetHost", None)
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    _ssh_private_key = attr_property("none.sshPrivateKey", None)
    _ssh_public_key = attr_property("none.sshPublicKey", None)
    _ssh_public_key_deployed = attr_property("none.sshPublicKeyDeployed", False, bool)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)

    @property
    def resource_id(self):
        return self.vm_id

    def get_physical_spec(self):
        return {
            ('config', 'users', 'extraUsers', 'root', 'openssh',
             'authorizedKeys', 'keys'): [self._ssh_public_key]
        } if self._ssh_public_key else {}

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, NoneDefinition)
        self.set_common_state(defn)
        self.target_host = defn._target_host
        self.public_ipv4 = defn._public_ipv4

        if not self.vm_id:
            self.log_start("generating new SSH keypair... ")
            key_name = "NixOps client key for {0}".format(self.name)
            self._ssh_private_key, self._ssh_public_key = \
                create_key_pair(key_name=key_name)
            self.log_end("done")
            self.vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)

    def switch_to_configuration(self, method, sync, command=None):
        res = super(NoneState, self).switch_to_configuration(method, sync, command)
        if res == 0:
            self._ssh_public_key_deployed = True
        return res

    def get_ssh_name(self):
        assert self.target_host
        return self.target_host

    def get_ssh_private_key_file(self):
        if self._ssh_private_key_file:
            return self._ssh_private_key_file
        else:
            return self.write_ssh_private_key(self._ssh_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_state_flags = super(NoneState, self).get_ssh_flags(*args, **kwargs)
        if self.vm_id and self.cur_toplevel and self._ssh_public_key_deployed:
            return super_state_flags + ["-o", "StrictHostKeyChecking=accept-new", "-i", self.get_ssh_private_key_file()]
        return super_state_flags

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return
        res.exists = True
        res.is_up = nixops.util.ping_tcp_port(self.target_host, self.ssh_port)
        if res.is_up:
            MachineState._check(self, res)

    def destroy(self, wipe=False):
        # No-op; just forget about the machine.
        return True
