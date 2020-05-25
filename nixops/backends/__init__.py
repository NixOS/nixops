# -*- coding: utf-8 -*-
from __future__ import annotations
import os
import re
from typing import Mapping, Any, List, Optional, Union, Sequence, TypeVar
from nixops.monkey import Protocol, runtime_checkable
import nixops.util
import nixops.resources
from nixops.state import RecordId
import subprocess
from ..command import format_command as _format_command
from typing_extensions import Protocol as PlainProtocol
import nixops.util
import nixops.transports.exceptions


class KeyOptions(nixops.resources.ResourceOptions):
    text: Optional[str]
    keyFile: Optional[str]
    keyCommand: Optional[Sequence[str]]
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


MachineDefinitionType = TypeVar(
    "MachineDefinitionType", bound="MachineDefinition", contravariant=True
)


class Transport(PlainProtocol):
    def __init__(self, machine: MachineState):
        pass

    def reset(self) -> None:
        pass

    @property
    def user(self) -> str:
        pass

    def upload_file(self, source: str, target: str, recursive: bool = False) -> None:
        pass

    def download_file(self, source: str, target: str, recursive: bool = False) -> None:
        pass

    def run_command(
        self,
        command: List[str],
        user: str,
        capture_stdout: bool = False,
        check: bool = False,
    ) -> nixops.util.ProcessResult:
        pass

    def copy_closure(self, path: str) -> None:
        pass


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

    _transport: Transport

    # The attr_proporty name is sshPinged for legacy reasons
    machine_pinged: bool = nixops.util.attr_property("sshPinged", False, bool)
    _machine_pinged_this_time: bool = False

    ssh_port: int = nixops.util.attr_property("targetPort", 22, int)
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

    # Time (in Unix epoch) the instance was started, if known.
    start_time: Optional[int] = nixops.util.attr_property("startTime", None, int)

    # The value of the ‘system.stateVersion’ attribute at the time the
    # machine was created.
    state_version: Optional[str] = nixops.util.attr_property("stateVersion", None, str)

    def __init__(self, depl, name: str, id: RecordId) -> None:
        super().__init__(depl, name, id)
        self._machine_pinged_this_time = False

        from nixops.transports.ssh import SSHTransport
        self._transport = SSHTransport(self)

        # from nixops.transports.noop import NoopTransport
        # self._transport = NoopTransport(self)

        self._ssh_private_key_file: Optional[str] = None
        self.new_toplevel: Optional[str] = None

    def prefix_definition(self, attr):
        return attr

    @property
    def started(self) -> bool:
        state = self.state
        return state == self.STARTING or state == self.UP

    def set_common_state(self, defn: MachineDefinitionType) -> None:
        self.keys = defn.keys
        self.ssh_port = defn.ssh_port
        self.ssh_user = defn.ssh_user
        self.ssh_options = defn.ssh_options
        self.has_fast_connection = defn.has_fast_connection
        self.provision_ssh_key = defn.provision_ssh_key

        # TODO: Reimplement with pluggable transport
        # if not self.has_fast_connection:
        #     self.ssh.enable_compression()

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
                .stdout.rstrip()
                .split(" ")
            )
            assert len(res) >= 3
            return res
        except nixops.transports.ConnectionFailed:
            return None
        except nixops.transports.CommandFailed:
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
            self.machine_pinged = True
            self._machine_pinged_this_time = True
            res.is_reachable = True
            res.load = avg

            # Get the systemd units that are in a failed state or in progress.
            out = self.run_command(
                "systemctl --all --full --no-legend", capture_stdout=True
            ).stdout.split("\n")
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
        self._transport.reset()

    def reboot_sync(self, hard: bool = False) -> None:
        """Reboot this machine and wait until it's up again."""
        self.reboot(hard=hard)
        self.log_start("waiting for the machine to finish rebooting...")
        nixops.util.wait_for_tcp_port(
            self.get_ssh_name(),
            self.ssh_port,
            open=False,
            callback=lambda: self.log_continue("."),
        )
        self.log_continue("[down]")
        nixops.util.wait_for_tcp_port(
            self.get_ssh_name(), self.ssh_port, callback=lambda: self.log_continue(".")
        )
        self.log_end("[up]")
        self.state = self.UP
        self.machine_pinged = True
        self._machine_pinged_this_time = True
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
            self.log("uploading key ‘{0}’...".format(k))
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

            outfile = destDir + "/" + k
            # We scp to a temporary file and then mv because scp is not atomic.
            # See https://github.com/NixOS/nixops/issues/762
            tmp_outfile = destDir + "/." + k + ".tmp"
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
            return ["-P", str(self.ssh_port)]
        else:
            return list(self.ssh_options) + ["-p", str(self.ssh_port)]

    def get_ssh_password(self):
        return None

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
        if self.machine_pinged and (not check or self._machine_pinged_this_time):
            return
        self.log_start("waiting for SSH...")
        nixops.util.wait_for_tcp_port(
            self.get_ssh_name(), self.ssh_port, callback=lambda: self.log_continue(".")
        )
        self.log_end("")
        if self.state != self.RESCUE:
            self.state = self.UP
        self.machine_pinged = True
        self._machine_pinged_this_time = True

    def write_ssh_private_key(self, private_key) -> str:
        key_file = "{0}/id_nixops-{1}".format(self.depl.tempdir, self.name)
        with os.fdopen(os.open(key_file, os.O_CREAT | os.O_WRONLY, 0o600), "w") as f:
            f.write(private_key)
        self._ssh_private_key_file = key_file
        return key_file

    def get_ssh_private_key_file(self) -> Optional[str]:
        return None

    def _logged_exec(self, command, **kwargs) -> nixops.util.ProcessResult:
        return nixops.util.logged_exec(command, self.logger, **kwargs)

    def run_command(
        self, command: str, allow_ssh_args: bool = False, **kwargs
    ) -> nixops.util.ProcessResult:
        """
        Execute a command on the machine via SSH.

        For possible keyword arguments, please have a look at
        nixops.ssh_util.SSH.run_command().
        """
        # If we are in rescue state, unset locale specific stuff, because we're
        # mainly operating in a chroot environment.
        if self.state == self.RESCUE:
            command = "export LANG= LC_ALL= LC_TIME=; " + command

        user: str
        try:
            user = kwargs.pop("user")
        except KeyError:
            user = self._transport.user

        cmd = _format_command(
            command,
            user=user,
            allow_ssh_args=allow_ssh_args,
            privilege_escalation_command=self.privilege_escalation_command,
        )

        return self._transport.run_command(cmd, user=user, **kwargs)

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
        return self.run_command(cmd, check=False).returncode

    def upload_file(self, source: str, target: str, recursive: bool = False):
        return self._transport.upload_file(source, target, recursive)

    def download_file(self, source: str, target: str, recursive: bool = False):
        return self._transport.download_file(source, target, recursive)

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
