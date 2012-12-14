# -*- coding: utf-8 -*-

import os
import sys
import time
import shutil
import atexit
import select
import subprocess
import charon.util
import charon.resources


class MachineDefinition(charon.resources.ResourceDefinition):
    """Base class for Charon machine definitions."""

    def __init__(self, xml):
        charon.resources.ResourceDefinition.__init__(self, xml)
        self.encrypted_links_to = set([e.get("value") for e in xml.findall("attrs/attr[@name='encryptedLinksTo']/list/string")])
        self.store_keys_on_machine = xml.find("attrs/attr[@name='storeKeysOnMachine']/bool").get("value") == "true"
        self.keys = {k.get("name"): k.find("string").get("value") for k in xml.findall("attrs/attr[@name='keys']/attrs/attr")}
        self.owners = [e.get("value") for e in xml.findall("attrs/attr[@name='owners']/list/string")]


class MachineState(charon.resources.ResourceState):
    """Base class for Charon machine state objects."""

    vm_id = charon.util.attr_property("vmId", None)
    ssh_pinged = charon.util.attr_property("sshPinged", False, bool)
    public_vpn_key = charon.util.attr_property("publicVpnKey", None)
    store_keys_on_machine = charon.util.attr_property("storeKeysOnMachine", True, bool)
    keys = charon.util.attr_property("keys", [], 'json')
    owners = charon.util.attr_property("owners", [], 'json')

    # Nix store path of the last global configuration deployed to this
    # machine.  Used to check whether this machine is up to date with
    # respect to the global configuration.
    cur_configs_path = charon.util.attr_property("configsPath", None)

    # Nix store path of the last machine configuration deployed to
    # this machine.
    cur_toplevel = charon.util.attr_property("toplevel", None)

    def __init__(self, depl, name, id):
        charon.resources.ResourceState.__init__(self, depl, name, id)
        self._ssh_pinged_this_time = False
        self._ssh_master_started = False
        self._ssh_master_opts = []
        self._ssh_private_key_file = None

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
        except SSHCommandFailed:
            return None

    def check(self):
        """Check machine state."""
        self.log_start("pinging SSH... ")
        avg = self.get_load_avg()
        if avg == None:
            self.log_end("unreachable")
            if self.state == self.UP: self.state = self.UNREACHABLE
        else:
            self.log_end("up [{0} {1} {2}]".format(avg[0], avg[1], avg[2]))
            self.state = self.UP
            self.ssh_pinged = True
            self._ssh_pinged_this_time = True

    def restore(self, defn, backup_id):
        """Restore persistent disks to a given backup, if possible."""
        self.warn("don't know how to restore disks from backup for machine ‘{0}’".format(self.name))

    def remove_backup(self, backup_id):
        """Remove a given backup of persistent disks, if possible."""
        self.warn("don't know how to remove a backup for machine ‘{0}’".format(self.name))

    def backup(self, backup_id):
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
        charon.util.wait_for_tcp_port(self.get_ssh_name(), 22, open=False, callback=lambda: self.log_continue("."))
        self.log_continue("[down]")
        charon.util.wait_for_tcp_port(self.get_ssh_name(), 22, callback=lambda: self.log_continue("."))
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
        charon.util.wait_for_tcp_port(self.get_ssh_name(), 22, callback=lambda: self.log_continue("."))
        self.log_end("")
        self.state = self.UP
        self.ssh_pinged = True
        self._ssh_pinged_this_time = True

    def _open_ssh_master(self):
        """Start an SSH master connection to speed up subsequent SSH sessions."""
        if self._ssh_master_started: return
        return

        # Start the master.
        control_socket = self.depl.tempdir + "/ssh-master-" + self.name
        res = subprocess.call(
            ["ssh", "-x", "root@" + self.get_ssh_name(), "-S", control_socket,
             "-M", "-N", "-f"]
            + self.get_ssh_flags())
        if res != 0:
            raise Exception("unable to start SSH master connection to ‘{0}’".format(self.name))

        # Kill the master on exit.
        atexit.register(
            lambda:
            subprocess.call(
                ["ssh", "root@" + self.get_ssh_name(),
                 "-S", control_socket, "-O", "exit"], stderr=charon.util.devnull)
            )

        self._ssh_master_opts = ["-S", control_socket]
        self._ssh_master_started = True

    def write_ssh_private_key(self, private_key):
        key_file = "{0}/id_charon-{1}".format(self.depl.tempdir, self.name)
        with os.fdopen(os.open(key_file, os.O_CREAT | os.O_WRONLY, 0600), "w") as f:
            f.write(private_key)
        self._ssh_private_key_file = key_file
        return key_file

    def _logged_exec(self, command, check=True, capture_stdout=False, stdin_string=None, env=None):
        stdin = subprocess.PIPE if stdin_string != None else charon.util.devnull

        if capture_stdout:
            process = subprocess.Popen(command, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            fds = [process.stdout, process.stderr]
            log_fd = process.stderr
        else:
            process = subprocess.Popen(command, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
            fds = [process.stdout]
            log_fd = process.stdout

        # FIXME: this can deadlock if stdin_string doesn't fit in the
        # kernel pipe buffer.
        if stdin_string != None: process.stdin.write(stdin_string)

        for fd in fds: charon.util.make_non_blocking(fd)

        at_new_line = True
        stdout = ""

        while len(fds) > 0:
            # The timeout/poll is to deal with processes (like
            # VBoxManage) that start children that go into the
            # background but keep the parent's stdout/stderr open,
            # preventing an EOF.  FIXME: Would be better to catch
            # SIGCHLD.
            (r, w, x) = select.select(fds, [], [], 1)
            if len(r) == 0 and process.poll() != None: break
            if capture_stdout and process.stdout in r:
                data = process.stdout.read()
                if data == "":
                    fds.remove(process.stdout)
                else:
                    stdout += data
            if log_fd in r:
                data = log_fd.read()
                if data == "":
                    if not at_new_line: self.log_end("")
                    fds.remove(log_fd)
                else:
                    start = 0
                    while start < len(data):
                        end = data.find('\n', start)
                        if end == -1:
                            self.log_start(data[start:])
                            at_new_line = False
                        else:
                            s = data[start:end]
                            if at_new_line:
                                self.log(s)
                            else:
                                self.log_end(s)
                            at_new_line = True
                        if end == -1: break
                        start = end + 1

        res = process.wait()

        if stdin_string != None: process.stdin.close()
        if check and res != 0:
            raise SSHCommandFailed("command ‘{0}’ failed on machine ‘{1}’".format(command, self.name))
        return stdout if capture_stdout else res

    def run_command(self, command, check=True, capture_stdout=False, stdin_string=None, timeout=None):
        """Execute a command on the machine via SSH."""
        self._open_ssh_master()
        cmdline = (
            ["ssh", "-x", "root@" + self.get_ssh_name()] +
            (["-o", "ConnectTimeout={0}".format(timeout)] if timeout else []) +
            self._ssh_master_opts + self.get_ssh_flags() + [command])
        return self._logged_exec(cmdline, check=check, capture_stdout=capture_stdout, stdin_string=stdin_string)

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
        env['NIX_SSHOPTS'] = ' '.join(self.get_ssh_flags());
        self._logged_exec(
            ["nix-copy-closure", "--to", "root@" + self.get_ssh_name(), path]
            + ([] if self.has_really_fast_connection() else ["--gzip"]),
            env=env)

    def has_really_fast_connection(self):
        return False

    def generate_vpn_key(self):
        if self.public_vpn_key: return
        (private, public) = charon.util.create_key_pair(key_name="Charon VPN key of {0}".format(self.name))
        f = open(self.depl.tempdir + "/id_vpn-" + self.name, "w+")
        f.write(private)
        f.seek(0)
        # FIXME: use run_command
        res = subprocess.call(
            ["ssh", "-x", "root@" + self.get_ssh_name()]
            + self.get_ssh_flags() +
            ["umask 077 && mkdir -p /root/.ssh && cat > /root/.ssh/id_charon_vpn"],
            stdin=f)
        f.close()
        if res != 0: raise Exception("unable to upload VPN key to ‘{0}’".format(self.name))
        self.public_vpn_key = public

    def upload_file(self, source, target, recursive=False):
        self._open_ssh_master()
        # FIXME: use ssh master
        if recursive:
            recursive_cmdline = [ '-r' ]
        else:
            recursive_cmdline = [ ]
        cmdline = ["scp"] +  self.get_ssh_flags() + recurisve_cmdline + [source, "root@" + self.get_ssh_name() + ":" + target]
        return self._logged_exec(cmdline)


class SSHCommandFailed(Exception):
    pass


import charon.backends.none
import charon.backends.virtualbox
import charon.backends.ec2
import charon.resources.ec2_keypair
import charon.resources.sqs_queue
import charon.resources.s3_bucket
import charon.resources.iam_role

def create_definition(xml):
    """Create a machine definition object from the given XML representation of the machine's attributes."""
    target_env = xml.find("attrs/attr[@name='targetEnv']/string").get("value")
    for i in [charon.backends.none.NoneDefinition,
              charon.backends.virtualbox.VirtualBoxDefinition,
              charon.backends.ec2.EC2Definition]:
        if target_env == i.get_type():
            return i(xml)
    raise Exception("unknown backend type ‘{0}’".format(target_env))

def create_state(depl, type, name, id):
    """Create a machine state object of the desired backend type."""
    for i in [charon.backends.none.NoneState,
              charon.backends.virtualbox.VirtualBoxState,
              charon.backends.ec2.EC2State,
              charon.resources.ec2_keypair.EC2KeyPairState,
              charon.resources.sqs_queue.SQSQueueState,
              charon.resources.iam_role.IAMRoleState,
              charon.resources.s3_bucket.S3BucketState]:
        if type == i.get_type():
            return i(depl, name, id)
    raise Exception("unknown backend type ‘{0}’".format(type))
