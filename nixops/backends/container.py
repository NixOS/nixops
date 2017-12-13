# -*- coding: utf-8 -*-

from nixops.backends import MachineDefinition, MachineState
import nixops.util
import nixops.ssh_util
import subprocess

class ContainerDefinition(MachineDefinition):
    """Definition of a NixOS container."""

    @classmethod
    def get_type(cls):
        return "container"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
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
    client_public_key = nixops.util.attr_property("container.clientPublicKey", None)
    public_host_key = nixops.util.attr_property("container.publicHostKey", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self.host_ssh = nixops.ssh_util.SSH(self.logger)
        self.host_ssh.register_host_fun(self.get_host_ssh)
        self.host_ssh.register_flag_fun(self.get_host_ssh_flags)

    @property
    def resource_id(self):
        return self.vm_id

    def address_to(self, m):
        if isinstance(m, ContainerState) and self.host == m.host:
            return m.private_ipv4
        return MachineState.address_to(self, m)

    def get_ssh_name(self):
        assert self.private_ipv4
        if self.host == "localhost":
            return self.private_ipv4
        else:
            return self.get_host_ssh() + "~" + self.private_ipv4

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.client_private_key)

    def get_ssh_flags(self, *args, **kwargs):
        # When using a remote container host, we have to proxy the ssh
        # connection to the container via the host.
        flags = super(ContainerState, self).get_ssh_flags(*args, **kwargs)
        flags += ["-i", self.get_ssh_private_key_file()]
        if self.host != "localhost":
            cmd = "ssh -x -a root@{0} {1} nc {2} {3}".format(self.get_host_ssh(), " ".join(self.get_host_ssh_flags()), self.private_ipv4, self.ssh_port)
            flags.extend(["-o", "ProxyCommand=" + cmd])
        return flags

    def get_ssh_for_copy_closure(self):
        # NixOS containers share the Nix store of the host, so we
        # should copy closures to the host.
        return self.host_ssh

    def copy_closure_to(self, path):
        if self.host == "localhost": return
        MachineState.copy_closure_to(self, path)

    def get_host_ssh(self):
        if self.host.startswith("__machine-"):
            m = self.depl.get_machine(self.host[10:])
            if not m.started:
                raise Exception("host machine ‘{0}’ of container ‘{1}’ is not up".format(m.name, self.name))
            return m.get_ssh_name()
        else:
            return self.host

    def get_host_ssh_flags(self):
        if self.host.startswith("__machine-"):
            m = self.depl.get_machine(self.host[10:])
            if not m.started:
                raise Exception("host machine ‘{0}’ of container ‘{1}’ is not up".format(m.name, self.name))
            return m.get_ssh_flags()
        else:
            return []

    def wait_for_ssh(self, check=False):
        return True

    # Run a command in the container via ‘nixos-container run’. Since
    # this uses ‘nsenter’, we don't need SSH in the container.
    def run_command(self, command, **kwargs):
        command = command.replace("'", r"'\''")
        return self.host_ssh.run_command(
            "nixos-container run {0} -- bash --login -c 'export HOME=/root; {1}'".format(self.vm_id, command),
            **kwargs)

    def get_physical_spec(self):
        return {('users', 'extraUsers', 'root', 'openssh', 'authorizedKeys', 'keys'): [self.client_public_key]}

    def create_after(self, resources, defn):
        host = defn.host if defn else self.host
        if host and host.startswith("__machine-"):
            return {self.depl.get_machine(host[10:])}
        else:
            return {}

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, ContainerDefinition)

        self.set_common_state(defn)

        if not self.client_private_key:
            (self.client_private_key, self.client_public_key) = nixops.util.create_key_pair()

        if self.vm_id is None:
            self.log("building initial configuration...")

            expr = " ".join([
                '{ imports = [ <nixops/container-base.nix> ];',
                '  boot.isContainer = true;',
                '  networking.hostName = "{0}";'.format(self.name),
                '  users.extraUsers.root.openssh.authorizedKeys.keys = [ "{0}" ];'.format(self.client_public_key),
                '}'])

            expr_file = self.depl.tempdir + "/{0}-initial.nix".format(self.name)
            nixops.util.write_file(expr_file, expr)

            path = subprocess.check_output(
                ["nix-build", "<nixpkgs/nixos>", "-A", "system",
                 "-I", "nixos-config={0}".format(expr_file)]
                + self.depl._nix_path_flags()).rstrip()

            self.log("creating container...")
            self.host = defn.host
            self.copy_closure_to(path)
            self.vm_id = self.host_ssh.run_command(
                "nixos-container create {0} --ensure-unique-name --system-path '{1}'"
                .format(self.name[:7], path), capture_stdout=True).rstrip()
            self.state = self.STOPPED

        if self.state == self.STOPPED:
            self.host_ssh.run_command("nixos-container start {0}".format(self.vm_id))
            self.state = self.UP

        if self.private_ipv4 is None:
            self.private_ipv4 = self.host_ssh.run_command("nixos-container show-ip {0}".format(self.vm_id), capture_stdout=True).rstrip()
            self.log("IP address is {0}".format(self.private_ipv4))

        if self.public_host_key is None:
            self.public_host_key = self.host_ssh.run_command("nixos-container show-host-key {0}".format(self.vm_id), capture_stdout=True).rstrip()
            nixops.known_hosts.add(self.get_ssh_name(), self.public_host_key)

    def destroy(self, wipe=False):
        if not self.vm_id: return True

        if not self.depl.logger.confirm("are you sure you want to destroy NixOS container ‘{0}’?".format(self.name)): return False

        nixops.known_hosts.remove(self.get_ssh_name(), self.public_host_key)

        self.host_ssh.run_command("nixos-container destroy {0}".format(self.vm_id))

        return True

    def stop(self):
        if not self.vm_id: return True
        self.log("stopping container...")
        self.state = self.STOPPING
        self.host_ssh.run_command("nixos-container stop {0}".format(self.vm_id))
        self.state = self.STOPPED

    def start(self):
        if not self.vm_id: return True
        self.log("starting container...")
        self.host_ssh.run_command("nixos-container start {0}".format(self.vm_id))
        self.state = self.STARTING

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        status = self.host_ssh.run_command("nixos-container status {0}".format(self.vm_id), capture_stdout=True).rstrip()

        if status == "gone":
            res.exists = False
            self.state = self.MISSING
            return

        res.exists = True

        if status == "down":
            res.is_up = False
            self.state = self.STOPPED
            return

        res.is_up = True
        MachineState._check(self, res)
