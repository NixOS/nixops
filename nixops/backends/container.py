# -*- coding: utf-8 -*-

from nixops.backends import MachineDefinition, MachineState
import nixops.ssh_util

class ContainerDefinition(MachineDefinition):
    """Definition of a NixOS container."""

    @classmethod
    def get_type(cls):
        return "container"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='container']/attrs")
        assert x is not None
        self.host = x.find("attr[@name='host']/string").get("value")

class ContainerState(MachineState):
    """State of a NixOS container."""

    @classmethod
    def get_type(cls):
        return "container"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)
    host = nixops.util.attr_property("container.host", None)
    client_private_key = nixops.util.attr_property("container.clientPrivateKey", None)
    client_public_key = nixops.util.attr_property("container.virtualbox.clientPublicKey", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self.host_ssh = nixops.ssh_util.SSH(self.logger)
        self.host_ssh.register_host_fun(lambda: self.host)

    @property
    def resource_id(self):
        return self.vm_id

    def get_ssh_name(self):
        assert self.private_ipv4
        return self.private_ipv4

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.client_private_key)

    def get_ssh_flags(self):
        return ["-o", "StrictHostKeyChecking=no", "-i", self.get_ssh_private_key_file()]

    def get_ssh_for_copy_closure(self):
        # NixOS containers share the Nix store of the host, so we
        # should copy closures to the host.
        return self.host_ssh

    def copy_closure_to(self, path):
        if self.host == "localhost": return
        MachineState.copy_closure_to(self, path)

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, ContainerDefinition)

        if not self.client_private_key:
            (self.client_private_key, self.client_public_key) = nixops.util.create_key_pair()

        if self.vm_id == None:
            self.log("creating NixOS container...")
            self.host = defn.host
            # FIXME: get rid of the flock.
            extra_config = " ".join([
                'services.openssh.enable = true;',
                'services.openssh.extraConfig = "UseDNS no";',
                'users.extraUsers.root.openssh.authorizedKeys.keys = [ "{0}" ];'.format(self.client_public_key)])
            self.vm_id = self.host_ssh.run_command(
                "NIX_PATH=nixpkgs=/home/eelco/Dev/nixpkgs-stable " +
                "nixos-container create {0} --ensure-unique-name --config '{1}'"
                .format(self.name, extra_config), capture_stdout=True).rstrip()
            self.state = self.STOPPED

        if self.state == self.STOPPED:
            self.host_ssh.run_command("nixos-container start {0}".format(self.vm_id))
            self.state = self.STARTING

        if self.private_ipv4 == None:
            self.private_ipv4 = self.host_ssh.run_command("nixos-container show-ip {0}".format(self.vm_id), capture_stdout=True).rstrip()
            self.log("IP address is {0}".format(self.private_ipv4))
            nixops.known_hosts.remove(self.private_ipv4)

    def destroy(self, wipe=False):
        if not self.vm_id: return True

        if not self.depl.logger.confirm("are you sure you want to destroy NixOS container ‘{0}’?".format(self.name)): return False

        # FIXME: handle the case where the container is already gone.
        self.host_ssh.run_command("nixos-container destroy {0}".format(self.vm_id))

        return True

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return
        # FIXME: do actual check.
        res.exists = True
        res.is_up = True
        MachineState._check(self, res)
