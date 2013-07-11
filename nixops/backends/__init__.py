# -*- coding: utf-8 -*-

import os
import re
import sys
import subprocess

import nixops.util
import nixops.resources
import nixops.ssh_util


class MachineDefinition(nixops.resources.ResourceDefinition):
    """Base class for NixOps machine definitions."""

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.encrypted_links_to = set([e.get("value") for e in xml.findall("attrs/attr[@name='encryptedLinksTo']/list/string")])
        self.store_keys_on_machine = xml.find("attrs/attr[@name='storeKeysOnMachine']/bool").get("value") == "true"
        self.keys = {k.get("name"): k.find("string").get("value") for k in xml.findall("attrs/attr[@name='keys']/attrs/attr")}
        self.owners = [e.get("value") for e in xml.findall("attrs/attr[@name='owners']/list/string")]


class MachineState(nixops.resources.ResourceState):
    """Base class for NixOps machine state objects."""

    vm_id = nixops.util.attr_property("vmId", None)
    ssh_pinged = nixops.util.attr_property("sshPinged", False, bool)
    public_vpn_key = nixops.util.attr_property("publicVpnKey", None)
    store_keys_on_machine = nixops.util.attr_property("storeKeysOnMachine", True, bool)
    keys = nixops.util.attr_property("keys", [], 'json')
    owners = nixops.util.attr_property("owners", [], 'json')

    # Nix store path of the last global configuration deployed to this
    # machine.  Used to check whether this machine is up to date with
    # respect to the global configuration.
    cur_configs_path = nixops.util.attr_property("configsPath", None)

    # Nix store path of the last machine configuration deployed to
    # this machine.
    cur_toplevel = nixops.util.attr_property("toplevel", None)

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._ssh_pinged_this_time = False
        self.ssh = nixops.ssh_util.SSH(self.logger)
        self.ssh.register_flag_fun(self.get_ssh_flags)
        self.ssh.register_host_fun(self.get_ssh_name)
        self.ssh.register_passwd_fun(self.get_ssh_password)
        self._ssh_private_key_file = None

    def get_definition_prefix(self):
        return ""

    @property
    def started(self):
        state = self.state
        return state == self.STARTING or state == self.UP

    def set_common_state(self, defn):
        self.store_keys_on_machine = defn.store_keys_on_machine
        self.keys = defn.keys

    def stop(self):
        """Stop this machine, if possible."""
        self.warn("don't know how to stop machine ‘{0}’".format(self.name))

    def start(self):
        """Start this machine, if possible."""
        pass

    def get_load_avg(self):
        """Get the load averages on the machine."""
        try:
            res = self.run_command("cat /proc/loadavg", capture_stdout=True, timeout=15).rstrip().split(' ')
            assert len(res) >= 3
            return res
        except nixops.ssh_util.SSHConnectionFailed:
            return None
        except nixops.ssh_util.SSHCommandFailed:
            return None

    # FIXME: Move this to ResourceState so that other kinds of
    # resources can be checked.
    def check(self):
        """Check machine state."""
        res = CheckResult()
        self._check(res)
        return res

    def _check(self, res):
        avg = self.get_load_avg()
        if avg == None:
            if self.state == self.UP: self.state = self.UNREACHABLE
            res.is_reachable = False
        else:
            self.state = self.UP
            self.ssh_pinged = True
            self._ssh_pinged_this_time = True
            res.is_reachable = True
            res.load = avg

            # Get the systemd units that are in a failed state.
            out = self.run_command("systemctl --all --full", capture_stdout=True).split('\n')
            res.failed_units = []
            for l in out:
                match = re.match("^([^ ]+) .* failed .*$", l)
                if match: res.failed_units.append(match.group(1))
                # Currently in systemd, failed mounts enter the
                # "inactive" rather than "failed" state.  So check for
                # that.  Hack: ignore special filesystems like
                # /sys/kernel/config.  Systemd tries to mount these
                # even when they don't exist.
                match = re.match("^([^\.]+\.mount) .* inactive .*$", l)
                if match and not match.group(1).startswith("sys-")  and not match.group(1).startswith("dev-"):
                    res.failed_units.append(match.group(1))

    def restore(self, defn, backup_id, devices=[]):
        """Restore persistent disks to a given backup, if possible."""
        self.warn("don't know how to restore disks from backup for machine ‘{0}’".format(self.name))

    def remove_backup(self, backup_id):
        """Remove a given backup of persistent disks, if possible."""
        self.warn("don't know how to remove a backup for machine ‘{0}’".format(self.name))

    def backup(self, defn, backup_id):
        """Make backup of persistent disks, if possible."""
        self.warn("don't know how to make backup of disks for machine ‘{0}’".format(self.name))

    def reboot(self):
        """Reboot this machine."""
        self.log("rebooting...")
        # The sleep is to prevent the reboot from causing the SSH
        # session to hang.
        self.run_command("(sleep 2; reboot) &")
        self.state = self.STARTING

    def reboot_sync(self):
        """Reboot this machine and wait until it's up again."""
        self.reboot()
        self.log_start("waiting for the machine to finish rebooting...")
        nixops.util.wait_for_tcp_port(self.get_ssh_name(), 22, open=False, callback=lambda: self.log_continue("."))
        self.log_continue("[down]")
        nixops.util.wait_for_tcp_port(self.get_ssh_name(), 22, callback=lambda: self.log_continue("."))
        self.log_end("[up]")
        self.state = self.UP
        self.ssh_pinged = True
        self._ssh_pinged_this_time = True
        self.send_keys()

    def send_keys(self):
        if self.store_keys_on_machine: return
        self.run_command("mkdir -m 0700 -p /run/keys")
        for k, v in self.get_keys().items():
            self.log("uploading key ‘{0}’...".format(k))
            tmp = self.depl.tempdir + "/key-" + self.name
            f = open(tmp, "w+"); f.write(v); f.close()
            self.upload_file(tmp, "/run/keys/" + k)
            os.remove(tmp)
        self.run_command("touch /run/keys/done")

    def get_keys(self):
        return self.keys

    def get_ssh_name(self):
        assert False

    def get_ssh_flags(self):
        return []

    def get_ssh_password(self):
        return None

    @property
    def public_ipv4(self):
        return None

    @property
    def private_ipv4(self):
        return None

    def address_to(self, m):
        """Return the IP address to be used to access machone "m" from this machine."""
        ip = m.public_ipv4
        if ip: return ip
        return None

    def wait_for_ssh(self, check=False):
        """Wait until the SSH port is open on this machine."""
        if self.ssh_pinged and (not check or self._ssh_pinged_this_time): return
        self.log_start("waiting for SSH...")
        nixops.util.wait_for_tcp_port(self.get_ssh_name(), 22, callback=lambda: self.log_continue("."))
        self.log_end("")
        if self.state != self.RESCUE:
            self.state = self.UP
        self.ssh_pinged = True
        self._ssh_pinged_this_time = True

    def write_ssh_private_key(self, private_key):
        key_file = "{0}/id_nixops-{1}".format(self.depl.tempdir, self.name)
        with os.fdopen(os.open(key_file, os.O_CREAT | os.O_WRONLY, 0600), "w") as f:
            f.write(private_key)
        self._ssh_private_key_file = key_file
        return key_file

    def get_ssh_private_key_file(self):
        return None

    def _logged_exec(self, command, **kwargs):
        return nixops.util.logged_exec(command, self.logger, **kwargs)

    def run_command(self, command, **kwargs):
        """
        Execute a command on the machine via SSH.

        For possible keyword arguments, please have a look at
        nixops.ssh_util.SSH.run_command().
        """
        # If we are in rescue state, unset locale specific stuff, because we're
        # mainly operating in a chroot environment.
        if self.state == self.RESCUE:
            command = "export LANG= LC_ALL= LC_TIME=; " + command
        return self.ssh.run_command(command, self.get_ssh_flags(), **kwargs)

    def switch_to_configuration(self, method, sync, command=None):
        """
        Execute the script to switch to new configuration.
        This function has to return an integer, which is the return value of the
        actual script.
        """
        cmd = ("NIXOS_NO_SYNC=1 " if not sync else "")
        if command is None:
            cmd += "/nix/var/nix/profiles/system/bin/switch-to-configuration"
        else:
            cmd += command
        cmd += " " + method
        return self.run_command(cmd, check=False)

    def copy_closure_to(self, path):
        """Copy a closure to this machine."""

        # !!! Implement copying between cloud machines, as in the Perl
        # version.

        # It's usually faster to let the target machine download
        # substitutes from nixos.org, so try that first.
        if not self.has_really_fast_connection():
            closure = subprocess.check_output(["nix-store", "-qR", path]).splitlines()
            self.run_command("nix-store -j 4 -r --ignore-unknown " + ' '.join(closure), check=False)

        # Any remaining paths are copied from the local machine.
        env = dict(os.environ)
        master = self.ssh.get_master()
        env['NIX_SSHOPTS'] = ' '.join(self.get_ssh_flags() + master.opts)
        self._logged_exec(
            ["nix-copy-closure", "--to", "root@" + self.get_ssh_name(), path]
            + ([] if self.has_really_fast_connection() else ["--gzip"]),
            env=env)

    def has_really_fast_connection(self):
        return False

    def generate_vpn_key(self):
        try:
            self.run_command("test -f /root/.ssh/id_charon_vpn")
            _vpn_key_exists = True
        except nixops.ssh_util.SSHCommandFailed:
            _vpn_key_exists = False

        if self.public_vpn_key and _vpn_key_exists: return
        (private, public) = nixops.util.create_key_pair(key_name="NixOps VPN key of {0}".format(self.name))
        f = open(self.depl.tempdir + "/id_vpn-" + self.name, "w+")
        f.write(private)
        f.seek(0)
        res = self.run_command("umask 077 && mkdir -p /root/.ssh &&"
                               " cat > /root/.ssh/id_charon_vpn",
                               check=False, stdin=f)
        if res != 0: raise Exception("unable to upload VPN key to ‘{0}’".format(self.name))
        self.public_vpn_key = public

    def upload_file(self, source, target, recursive=False):
        master = self.ssh.get_master()
        cmdline = ["scp"] + self.get_ssh_flags() + master.opts
        if recursive:
            cmdline += ['-r']
        cmdline += [source, "root@" + self.get_ssh_name() + ":" + target]
        return self._logged_exec(cmdline)

    def download_file(self, source, target, recursive=False):
        master = self.ssh.get_master()
        cmdline = ["scp"] + self.get_ssh_flags() + master.opts
        if recursive:
            cmdline += ['-r']
        cmdline += ["root@" + self.get_ssh_name() + ":" + source, target]
        return self._logged_exec(cmdline)

    def get_console_output(self):
        return "(not available for this machine type)\n"


class CheckResult(object):
    def __init__(self):
        # Whether the resource exists.
        self.exists = None

        # Whether the resource is "up".  Generally only meaningful for
        # machines.
        self.is_up = None

        # Whether the resource is reachable via SSH.
        self.is_reachable = None

        # Whether the disks that should be attached to a machine are
        # in fact properly attached.
        self.disks_ok = None

        # List of systemd units that are in a failed state.
        self.failed_units = None

        # Load average on the machine.
        self.load = None

        # Error messages.
        self.messages = []

        # FIXME: add a check whether the active NixOS config on the
        # machine is correct.


import nixops.backends.none
import nixops.backends.virtualbox
import nixops.backends.ec2
import nixops.backends.hetzner
import nixops.resources.ec2_keypair
import nixops.resources.sqs_queue
import nixops.resources.s3_bucket
import nixops.resources.iam_role

def create_definition(xml):
    """Create a machine definition object from the given XML representation of the machine's attributes."""
    target_env = xml.find("attrs/attr[@name='targetEnv']/string").get("value")
    for i in [nixops.backends.none.NoneDefinition,
              nixops.backends.virtualbox.VirtualBoxDefinition,
              nixops.backends.ec2.EC2Definition,
              nixops.backends.hetzner.HetznerDefinition]:
        if target_env == i.get_type():
            return i(xml)
    raise nixops.deployment.UnknownBackend("unknown backend type ‘{0}’".format(target_env))

def create_state(depl, type, name, id):
    """Create a machine state object of the desired backend type."""
    for i in [nixops.backends.none.NoneState,
              nixops.backends.virtualbox.VirtualBoxState,
              nixops.backends.ec2.EC2State,
              nixops.backends.hetzner.HetznerState,
              nixops.resources.ec2_keypair.EC2KeyPairState,
              nixops.resources.sqs_queue.SQSQueueState,
              nixops.resources.iam_role.IAMRoleState,
              nixops.resources.s3_bucket.S3BucketState]:
        if type == i.get_type():
            return i(depl, name, id)
    raise nixops.deployment.UnknownBackend("unknown backend type ‘{0}’".format(type))
