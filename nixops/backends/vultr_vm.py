# -*- coding: utf-8 -*-
"""
A backend for Vultr.

Vultr doesn't have an official nixos image. To use this backend you must
follow the instructions here to generate a snapshot:
    https://www.vultr.com/docs/install-nixos-on-vultr

Still to do:
* Use nixos OS type when Vultr adds one.
"""
import os
import os.path
import time
import nixops.resources
from nixops.backends import MachineDefinition, MachineState
from nixops.nix_expr import Function, RawValue
import nixops.util
import nixops.known_hosts
import socket
from vultr import Vultr, VultrError
from json import dumps

class VultrDefinition(MachineDefinition):
    @classmethod
    def get_type(cls):
        return "vultr"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        self.dcid = config["vultr"]["dcid"]
        self.vpsplanid = config["vultr"]["vpsplanid"]
        self.snapshotid = config["vultr"]["snapshotid"]
        self.label = config["vultr"]["label"]
        # TODO: only use 164 if snapshotid is set.
        self.osid = 164

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.dcid)


class VultrState(MachineState):
    @classmethod
    def get_type(cls):
        return "vultr"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    apikey = nixops.util.attr_property("vultr.apikey", None)
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    default_gateway = nixops.util.attr_property("defaultGateway", None)
    netmask = nixops.util.attr_property("netmask", None)
    subid = nixops.util.attr_property("vultr.subid", None)
    label = nixops.util.attr_property("vultr.label", None)
    _ssh_private_key = nixops.util.attr_property("vultr.sshPrivateKey", None)
    _ssh_public_key = nixops.util.attr_property("vultr.sshPublicKey", None)
    _ssh_public_key_deployed = nixops.util.attr_property("vultr.sshPublicKeyDeployed", False, bool)
    # TODO: only use 164 if snapshotid is set.
    osid = 164

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self.name = name

    def get_ssh_name(self):
        return self.public_ipv4

    def get_ssh_flags(self, *args, **kwargs):
        super_state_flags = super(VultrState, self).get_ssh_flags(*args, **kwargs)
        if self.subid and self._ssh_public_key_deployed:
            return super_state_flags + [
                '-o', 'UserKnownHostsFile=/dev/null',
                '-o', 'StrictHostKeyChecking=no',
                '-i', self.get_ssh_private_key_file(),
            ]
        return super_state_flags

    def get_physical_spec(self):
        return Function("{ ... }", {
            'imports': [ RawValue('<nixpkgs/nixos/modules/profiles/qemu-guest.nix>') ],
            ('config', 'boot', 'initrd', 'availableKernelModules'): [ "ata_piix", "uhci_hcd", "virtio_pci", "sr_mod", "virtio_blk" ],
            ('config', 'boot', 'loader', 'grub', 'device'): '/dev/vda',
            ('config', 'fileSystems', '/'): { 'device': '/dev/vda1', 'fsType': 'btrfs'},
            ('config', 'users', 'extraUsers', 'root', 'openssh', 'authorizedKeys', 'keys'): [self._ssh_public_key]
        })

    def get_ssh_private_key_file(self):
        if self._ssh_private_key_file:
            return self._ssh_private_key_file
        else:
            return self.write_ssh_private_key(self._ssh_private_key)

    def create_after(self, resources, defn):
        # make sure the ssh key exists before we do anything else
        return {
            r for r in resources if
            isinstance(r, nixops.resources.ssh_keypair.SSHKeyPairState)
        }

    def get_api_key(self):
        apikey = os.environ.get('VULTR_API_KEY', self.apikey)
        if apikey == None:
            raise Exception("VULTR_API_KEY must be set in the environment to deploy instances")
        return apikey


    def destroy(self, wipe=False):
        self.log("destroying instance {}".format(self.subid))
        vultr = Vultr(self.get_api_key())
        try:
            vultr.server_destroy(self.subid)
        except VultrError:
            self.log("An error occurred destroying instance. Assuming it's been destroyed already.")
        self.public_ipv4 = None
        self.subid = None

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.set_common_state(defn)

        if self.subid is not None:
            return

        self.log_start("creating instance ...")
        self.log("dcid: " + str(defn.dcid))
        self.log("osid: " + str(defn.osid))
        self.log("vpsplanid: " + str(defn.vpsplanid))
        self.log("snapshotid: " + str(defn.snapshotid))
        self.log("label: " + str(defn.label))
        vultr = Vultr(self.get_api_key())
        snapshots = vultr.snapshot_list()
        if defn.snapshotid not in snapshots:
            raise Exception("Unexpected Error: snapshot {} does not exist".format(defn.snapshotid))
        server_create_output = vultr.server_create(dcid=defn.dcid, osid=defn.osid, vpsplanid=defn.vpsplanid, snapshotid=defn.snapshotid, enable_ipv6='yes', enable_private_network='yes', label=defn.label)
        subid = server_create_output['SUBID']
        self.log("instance id: " + subid)
        server_info = vultr.server_list()[subid]
        while server_info['status'] == 'pending' or server_info['server_state'] != 'ok':
            server_info = vultr.server_list()[subid]
            time.sleep(1)
            self.log_continue("[status: {} state: {}] ".format(server_info['status'], server_info['server_state']))
            if server_info['status'] == 'active' and server_info['server_state'] == 'ok':
                # vultr sets ok before locked when restoring snapshot. Need to make sure we're really ready.
                time.sleep(10)
                server_info = vultr.server_list()[subid]
        if server_info['status'] != 'active' or server_info['server_state'] != 'ok':
            raise Exception("unexpected status: {}/{}".format(server_info['status'],server_info['server_state']))
        self.subid = subid
        self.label = server_info['label']
        self.log_start("generating new SSH keypair... ")
        key_name = "NixOps client key for {0}".format(self.subid)
        self._ssh_private_key, self._ssh_public_key = \
            nixops.util.create_key_pair(key_name=key_name)
        self.public_ipv4 = server_info['main_ip']
        self.log_end("{}".format(self.public_ipv4))
        self.default_gateway = server_info['gateway_v4']
        self.netmask = server_info['netmask_v4']
        self.wait_for_ssh()

    def switch_to_configuration(self, method, sync, command=None):
        res = super(VultrState, self).switch_to_configuration(method, sync, command)
        if res == 0:
            self._ssh_public_key_deployed = True
        return res

