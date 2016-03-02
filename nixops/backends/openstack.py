# -*- coding: utf-8 -*-

import os

from nixops.backends import MachineDefinition, MachineState
import nixops.util
import shade


class OpenStackServerDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "openstack"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        self.cloudname = config["cloudname"]


class OpenStackServerState(MachineState):
    """ State of an OpenStack machine."""

    client_public_key = nixops.util.attr_property("openstack.clientPublicKey", None)
    client_private_key = nixops.util.attr_property("openstack.clientPrivateKey", None)
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)

    @classmethod
    def get_type(cls):
        return "openstack"

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        """ Shade uses os-client-config for authentication information """
        shade.simple_logging(debug=True)
        cloudname = nixops.util.attr_property("openstack.cloud", None)
        self.cloud = shade.openstack_clouds(name=cloudname)
        self.image = None

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.client_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(OpenStackServerState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ["-o", "StrictHostKeyChecking=no",
                              "-i", self.get_ssh_private_key_file()]

    def _vm_id(self):
        return "nixops-{0}-{1}".format(self.depl.uuid, self.name)

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.log("starting openstack machine...")
        assert isinstance(defn, OpenStackServerDefinition)
        self.set_common_state(defn)

        if not self.client_public_key:
            (self.client_private_key, self.client_public_key) = nixops.util.create_key_pair()

        if self.vm_id is None:
            os.putenv("NIXOPS_LIBVIRTD_PUBKEY", self.client_public_key)
            vm_id = self._vm_id()
            base_image = self._logged_exec(
                ["nix-build"] + self.depl._eval_flags(self.depl.nix_exprs) +
                ["--arg", "checkConfigurationOptions", "false",
                 "-A", "nodes.{0}.config.deployment.libvirtd.baseImage".format(self.name),
                 "-o", "{0}/libvirtd-image-{1}".format(self.depl.tempdir, self.name)],
                capture_stdout=True).rstrip()
            self.image = self.cloud.create_image(vm_id, filename="{0}/disk.qcow2".format(base_image), wait=True)

            self.vm_id = self._vm_id()
        self.start()
        return True

    def has_really_fast_connection(self):
        return True

    def _is_running(self):
        vm = self.cloud.get_server(self.vm_id)
        if vm is None:
            return False
        else:
            return True

    def start(self):
        self.log("starting...")
        assert self.vm_id
        if self._is_running():
            self.private_ipv4 = shade.meta.get_server_private_ip(self.cloud.get_server(self.vm_id))
            self.public_ipv4 = shade.meta.get_server_external_ipv4(self.cloud.get_server(self.vm_id))
        else:
            flavor = self.cloud.get_flavor_by_ram(512)
            self.cloud.create_server(self.vm_id, image=self.image['id'], flavor=flavor['id'], wait=True, auto_ip=True)

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4

    def stop(self):
        assert self.vm_id
        if self._is_running():
            self.log_start("shutting down... ")
            self.cloud.delete_server(self.vm_id)
        else:
            self.log("not running")

    def destroy(self, wipe=False):
        if not self.vm_id:
            return True
        self.log_start("destroying... ")
        self.stop()
        return True
