# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import re
from typing import Mapping, Any, List, Optional, Union, Sequence, TypeVar, Callable
from nixops.monkey import Protocol, runtime_checkable
import nixops.util
import nixops.resources
import nixops.ssh_util
from nixops.state import RecordId
import subprocess
import threading


class KeyOptions(nixops.resources.ResourceOptions):
    text: Optional[str]
    keyFile: Optional[str]
    keyCommand: Optional[Sequence[str]]
    name: str
    path: str
    destDir: str
    user: str
    group: str
    permissions: str


class MachineOptions(nixops.resources.ResourceOptions):
    targetPort: int
    alwaysActivate: bool
    owners: Sequence[str]
    hasFastConnection: bool
    keys: Mapping[str, KeyOptions]
    nixosRelease: str
    targetUser: Optional[str]
    sshOptions: Sequence[str]
    privilegeEscalationCommand: Sequence[str]


class MachineDefinition(nixops.resources.ResourceDefinition):
    """Base class for NixOps machine definitions."""

    config: MachineOptions

    ssh_port: int
    always_activate: bool
    owners: List[str]
    has_fast_connection: bool
    keys: Mapping[str, KeyOptions]
    ssh_user: str
    ssh_options: List[str]
    privilege_escalation_command: List[str]
    provision_ssh_key: bool

    def __init__(self, name: str, config: nixops.resources.ResourceEval):
        super().__init__(name, config)
        self.ssh_port = config["targetPort"]
        self.always_activate = config["alwaysActivate"]
        self.owners = config["owners"]
        self.has_fast_connection = config["hasFastConnection"]
        self.keys = {k: KeyOptions(**v) for k, v in config["keys"].items()}
        self.ssh_options = config["sshOptions"]

        self.ssh_user = config["targetUser"]

        self.privilege_escalation_command = config["privilegeEscalationCommand"]
        self.provision_ssh_key = config["provisionSSHKey"]


MachineDefinitionType = TypeVar("MachineDefinitionType", bound="MachineDefinition")


@runtime_checkable
class MachineState(
    nixops.resources.ResourceState[MachineDefinitionType],
    Protocol[MachineDefinitionType],
):
    """Base class for NixOps machine state objects."""

    vm_id: Optional[str] = nixops.util.attr_property("vmId", None)
    has_fast_connection: bool = nixops.util.attr_property(
        "hasFastConnection", False, bool
    )

    ssh: nixops.ssh_util.SSH
    ssh_pinged: bool = nixops.util.attr_property("sshPinged", False, bool)
    _ssh_pinged_this_time: bool = False
    ssh_port: int = nixops.util.attr_property("targetPort", None, int)
    ssh_user: str = nixops.util.attr_property("targetUser", "root", str)
    ssh_options: List[str] = nixops.util.attr_property("sshOptions", [], "json")
    privilege_escalation_command: List[str] = nixops.util.attr_property(
        "privilegeEscalationCommand", [], "json"
    )
    _ssh_private_key_file: Optional[str]
    provision_ssh_key: bool = nixops.util.attr_property("provisionSSHKey", True, bool)
    public_vpn_key: Optional[str] = nixops.util.attr_property("publicVpnKey", None)
    keys: Mapping[str, KeyOptions] = nixops.util.attr_property("keys", {}, "json")
    owners: List[str] = nixops.util.attr_property("owners", [], "json")

    # Nix store path of the last global configuration deployed to this
    # machine.  Used to check whether this machine is up to date with
    # respect to the global configuration.
    cur_configs_path: Optional[str] = nixops.util.attr_property("configsPath", None)

    # Nix store path of the last machine configuration deployed to
    # this machine.
    cur_toplevel: Optional[str] = nixops.util.attr_property("toplevel", None)
    new_toplevel: Optional[str]

    # Immutable flake URI from which this machine was built.
    cur_flake_uri: Optional[str] = nixops.util.attr_property("curFlakeUri", None)

    # Time (in Unix epoch) the instance was started, if known.
    start_time: Optional[int] = nixops.util.attr_property("startTime", None, int)

    # The value of the ‘system.stateVersion’ attribute at the time the
    # machine was created.
    state_version: Optional[str] = nixops.util.attr_property("stateVersion", None, str)

    defn: Optional[MachineDefinition] = None

    def __init__(self, depl, name: str, id: RecordId) -> None:
        super().__init__(depl, name, id)
        self.defn = None
        self._ssh_pinged_this_time = False
        self.ssh = nixops.ssh_util.SSH(self.logger)
        self.ssh.register_flag_fun(self.get_ssh_flags)
        self.ssh.register_host_fun(self.get_ssh_name)
        self.ssh.register_passwd_fun(self.get_ssh_password)
        self._ssh_private_key_file: Optional[str] = None
        self.new_toplevel: Optional[str] = None
        self.ssh.privilege_escalation_command = self.privilege_escalation_command

    def prefix_definition(self, attr):
        return attr

    @property
    def started(self) -> bool:
        state = self.state
        return state == self.STARTING or state == self.UP

    def set_common_state(self, defn: MachineDefinitionType) -> None:
        self.defn = defn
        self.keys = defn.keys
        self.ssh_port = defn.ssh_port
        self.ssh_user = defn.ssh_user
        self.ssh_options = defn.ssh_options
        self.has_fast_connection = defn.has_fast_connection
        self.provision_ssh_key = defn.provision_ssh_key
        if not self.has_fast_connection:
            self.ssh.enable_compression()

        self.ssh.privilege_escalation_command = list(defn.privilege_escalation_command)
        self.privilege_escalation_command = list(defn.privilege_escalation_command)

    def stop(self) -> None:
        """Stop this machine, if possible."""
        self.warn("don't know how to stop machine ‘{0}’".format(self.name))

    def start(self) -> None:
        """Start this machine, if possible."""
        pass

    def get_load_avg(self) -> Union[List[str], None]:
        """Get the load averages on the machine."""
        try:
            res = (
                self.run_command("cat /proc/loadavg", capture_stdout=True, timeout=15)
                .rstrip()
                .split(" ")
            )
            assert len(res) >= 3
            return res
        except nixops.ssh_util.SSHConnectionFailed:
            return None
        except nixops.ssh_util.SSHCommandFailed:
            return None

    # FIXME: Move this to ResourceState so that other kinds of
    # resources can be checked.
    def check(self):  # TODO -> CheckResult, but supertype ResourceState -> True
        """Check machine state."""
        res = CheckResult()
        self._check(res)
        return res

    def _check(self, res):  # TODO -> None but supertype ResourceState -> True
        avg = self.get_load_avg()
        if avg is None:
            if self.state == self.UP:
                self.state = self.UNREACHABLE
            res.is_reachable = False
        else:
            self.state = self.UP
            self.ssh_pinged = True
            self._ssh_pinged_this_time = True
            res.is_reachable = True
            res.load = avg

            # Get the systemd units that are in a failed state or in progress.
            out = self.run_command(
                "systemctl --all --full --no-legend", capture_stdout=True
            ).split("\n")
            res.failed_units = []
            res.in_progress_units = []
            for line in out:
                match = re.match("^([^ ]+) .* failed .*$", line)
                if match:
                    res.failed_units.append(match.group(1))

                # services that are in progress
                match = re.match("^([^ ]+) .* activating .*$", line)
                if match:
                    res.in_progress_units.append(match.group(1))

                # Currently in systemd, failed mounts enter the
                # "inactive" rather than "failed" state.  So check for
                # that.  Hack: ignore special filesystems like
                # /sys/kernel/config and /tmp. Systemd tries to mount these
                # even when they don't exist.
                match = re.match("^([^\.]+\.mount) .* inactive .*$", line)  # noqa: W605
                if (
                    match
                    and not match.group(1).startswith("sys-")
                    and not match.group(1).startswith("dev-")
                    and not match.group(1) == "tmp.mount"
                ):
                    res.failed_units.append(match.group(1))

                if match and match.group(1) == "tmp.mount":
                    try:
                        self.run_command(
                            "cat /etc/fstab | cut -d' ' -f 2 | grep '^/tmp$' &> /dev/null"
                        )
                    except Exception:
                        continue
                    res.failed_units.append(match.group(1))

    def restore(self, defn, backup_id: Optional[str], devices: List[str] = []):
        """Restore persistent disks to a given backup, if possible."""
        self.warn(
            "don't know how to restore disks from backup for machine ‘{0}’".format(
                self.name
            )
        )

    def remove_backup(self, backup_id, keep_physical=False):
        """Remove a given backup of persistent disks, if possible."""
        self.warn(
            "don't know how to remove a backup for machine ‘{0}’".format(self.name)
        )

    def get_backups(self) -> Mapping[str, Mapping[str, Any]]:
        self.warn("don't know how to list backups for ‘{0}’".format(self.name))
        return {}

    def backup(self, defn, backup_id: str, devices: List[str] = []) -> None:
        """Make backup of persistent disks, if possible."""
        self.warn(
            "don't know how to make backup of disks for machine ‘{0}’".format(self.name)
        )

    def reboot(self, hard: bool = False) -> None:
        """Reboot this machine."""
        self.log("rebooting...")
        if self.state == self.RESCUE:
            # We're on non-NixOS here, so systemd might not be available.
            # The sleep is to prevent the reboot from causing the SSH
            # session to hang.
            reboot_command = "(sleep 2; reboot) &"
        else:
            reboot_command = "systemctl reboot"
        self.run_command(reboot_command, check=False)
        self.state = self.STARTING
        self.ssh.reset()

    def ping(self) -> bool:
        event = threading.Event()

        def _worker():
            try:
                self.ssh.run_command(
                    ["true"],
                    user=self.ssh_user,
                    timeout=1,
                    logged=False,
                    connection_tries=1,
                    ssh_quiet=True,
                )
            except Exception:
                return False
            else:
                event.set()

        t = threading.Thread(target=_worker)
        t.start()

        return event.wait(timeout=1)

    def _ping(self) -> None:
        """Wrap ping() so we can check for success via exceptions"""
        if not self.ping():
            raise ValueError("Did not return True")

    def wait_for_up(
        self,
        timeout: Optional[int] = None,
        callback: Optional[Callable[[], Any]] = None,
    ) -> None:
        nixops.util.wait_for_success(self._ping, timeout=timeout, callback=callback)
        self.ssh.reset()  # To avoid passing a stderr suppressed master conn forward

    def wait_for_down(
        self,
        timeout: Optional[int] = None,
        callback: Optional[Callable[[], Any]] = None,
    ) -> None:
        nixops.util.wait_for_fail(self._ping, timeout=timeout, callback=callback)
        self.ssh.reset()  # To avoid passing a stderr suppressed master conn forward

    def reboot_sync(self, hard: bool = False) -> None:
        """Reboot this machine and wait until it's up again."""
        self.reboot(hard=hard)
        self.log_start("waiting for the machine to finish rebooting...")

        def progress_cb() -> None:
            self.log_continue(".")

        self.wait_for_down(callback=progress_cb)

        self.log_continue("[down]")

        self.wait_for_up(callback=progress_cb)

        self.log_end("[up]")
        self.state = self.UP
        self.ssh_pinged = True
        self._ssh_pinged_this_time = True
        self.send_keys()

    def reboot_rescue(self, hard: bool = False) -> None:
        """
        Reboot machine into rescue system and wait until it is active.
        """
        self.warn("machine ‘{0}’ doesn't have a rescue" " system.".format(self.name))

    def send_keys(self) -> None:
        if self.state == self.RESCUE:
            # Don't send keys when in RESCUE state, because we're most likely
            # bootstrapping plus we probably don't have /run mounted properly
            # so keys will probably end up being written to DISK instead of
            # into memory.
            return

        for k, opts in self.get_keys().items():
            self.log("uploading key ‘{0}’ to ‘{1}’...".format(k, opts["path"]))
            tmp = self.depl.tempdir + "/key-" + self.name

            destDir = opts["destDir"].rstrip("/")
            self.run_command(
                (
                    "test -d '{0}' || ("
                    " mkdir -m 0750 -p '{0}' &&"
                    " chown root:keys  '{0}';)"
                ).format(destDir)
            )

            if opts.get("text") is not None:
                with open(tmp, "w+") as f:
                    f.write(opts["text"])
            elif opts.get("keyFile") is not None:
                self._logged_exec(["cp", opts["keyFile"], tmp])
            elif opts.get("keyCommand") is not None:
                try:
                    with open(tmp, "w+") as f:
                        subprocess.run(opts["keyCommand"], stdout=f, check=True)
                except subprocess.CalledProcessError:
                    self.warn(f"Running command to generate key '{k}' failed:")
                    raise
            else:
                raise Exception(
                    "Neither 'text', 'keyFile', nor 'keyCommand' options were set for key '{0}'.".format(
                        k
                    )
                )

            outfile = opts["path"]
            # We scp to a temporary file and then mv because scp is not atomic.
            # See https://github.com/NixOS/nixops/issues/762
            tmp_outfile = destDir + "/." + opts["name"] + ".tmp"
            outfile_esc = "'" + outfile.replace("'", r"'\''") + "'"
            tmp_outfile_esc = "'" + tmp_outfile.replace("'", r"'\''") + "'"
            self.run_command("rm -f " + outfile_esc + " " + tmp_outfile_esc)
            self.upload_file(tmp, tmp_outfile)
            # For permissions we use the temporary file as well, so that
            # the final outfile will appear atomically with the right permissions.
            self.run_command(
                " ".join(
                    [
                        # chown only if user and group exist,
                        # else leave root:root owned
                        "(",
                        " getent passwd '{1}' >/dev/null &&",
                        " getent group '{2}' >/dev/null &&",
                        " chown '{1}:{2}' {0}",
                        ");",
                        # chmod either way
                        "chmod '{3}' {0}",
                    ]
                ).format(
                    tmp_outfile_esc, opts["user"], opts["group"], opts["permissions"]
                )
            )
            self.run_command("mv " + tmp_outfile_esc + " " + outfile_esc)
            os.remove(tmp)
        self.run_command(
            "mkdir -m 0750 -p /run/keys && "
            "chown root:keys  /run/keys && "
            "touch /run/keys/done"
        )

    def get_keys(self):
        return self.keys

    def get_ssh_name(self):
        assert False

    def get_ssh_flags(self, scp=False) -> List[str]:
        if scp:
            return ["-P", str(self.ssh_port)] if self.ssh_port is not None else []
        else:
            return list(self.ssh_options) + (
                ["-p", str(self.ssh_port)] if self.ssh_port is not None else []
            )

    def get_ssh_password(self):
        return None

    def get_ssh_for_copy_closure(self):
        return self.ssh

    @property
    def public_host_key(self):
        return None

    @property
    def private_ipv4(self) -> Optional[str]:
        return None

    def address_to(self, r):
        """Return the IP address to be used to access resource "r" from this machine."""
        return r.public_ipv4

    def wait_for_ssh(self, check=False):
        """Wait until the SSH port is open on this machine."""
        if self.ssh_pinged and (not check or self._ssh_pinged_this_time):
            return
        self.log_start("waiting for SSH...")

        self.wait_for_up(callback=lambda: self.log_continue("."))

        self.log_end("")
        if self.state != self.RESCUE:
            self.state = self.UP
        self.ssh_pinged = True
        self._ssh_pinged_this_time = True

    def write_ssh_private_key(self, private_key) -> str:
        key_file = "{0}/id_nixops-{1}".format(self.depl.tempdir, self.name)
        with os.fdopen(os.open(key_file, os.O_CREAT | os.O_WRONLY, 0o600), "w") as f:
            f.write(private_key)
        self._ssh_private_key_file = key_file
        return key_file

    def get_ssh_private_key_file(self) -> Optional[str]:
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
        return self.ssh.run_command(
            command, flags=self.get_ssh_flags(), user=self.ssh_user, **kwargs
        )

    def switch_to_configuration(
        self, method: str, sync: bool, command: Optional[str] = None
    ) -> int:
        """
        Execute the script to switch to new configuration.
        This function has to return an integer, which is the return value of the
        actual script.
        """
        cmd = "NIXOS_NO_SYNC=1 " if not sync else ""
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

        ssh = self.get_ssh_for_copy_closure()

        # Any remaining paths are copied from the local machine.
        env = dict(os.environ)
        env["NIX_SSHOPTS"] = " ".join(
            ssh._get_flags() + ssh.get_master(user=self.ssh_user).opts
        )
        self._logged_exec(
            ["nix-copy-closure", "--to", ssh._get_target(user=self.ssh_user), path]
            + ([] if self.has_fast_connection else ["--use-substitutes"]),
            env=env,
        )

    def _get_scp_name(self) -> str:
        ssh_name = self.get_ssh_name()
        # ipv6 addresses have to be wrapped in brackets for scp
        if ":" in ssh_name:
            return "[%s]" % (ssh_name)
        return ssh_name

    def _fmt_rsync_command(self, *args: str, recursive: bool = False) -> List[str]:
        master = self.ssh.get_master(user=self.ssh_user)

        ssh_cmdline: List[str] = ["ssh"] + self.get_ssh_flags() + master.opts
        cmdline = ["rsync", "-e", nixops.util.shlex_join(ssh_cmdline)]

        if self.ssh_user != "root":
            cmdline.extend(
                [
                    "--rsync-path",
                    nixops.util.shlex_join(
                        self.ssh.privilege_escalation_command + ["rsync"]
                    ),
                ]
            )

        if recursive:
            cmdline += ["-r"]

        cmdline.extend(args)

        return cmdline

    def upload_file(self, source: str, target: str, recursive: bool = False):
        cmdline = self._fmt_rsync_command(
            source,
            self.ssh_user + "@" + self._get_scp_name() + ":" + target,
            recursive=recursive,
        )
        return self._logged_exec(cmdline)

    def download_file(self, source: str, target: str, recursive: bool = False):
        cmdline = self._fmt_rsync_command(
            self.ssh_user + "@" + self._get_scp_name() + ":" + source,
            target,
            recursive=recursive,
        )
        return self._logged_exec(cmdline)

    def get_console_output(self):
        return "(not available for this machine type)\n"


class CheckResult(object):
    def __init__(self) -> None:
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

        # List of systemd units that are in progress.
        self.in_progress_units = None

        # Load average on the machine.
        self.load = None

        # Error messages.
        self.messages: List[str] = []

        # FIXME: add a check whether the active NixOS config on the
        # machine is correct.


GenericMachineState = MachineState[MachineDefinition]
