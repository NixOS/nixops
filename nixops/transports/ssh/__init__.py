from typing import List
import nixops.util
import os
from .ssh import SSH
from typing import Iterable


__all__ = (
    "ConnectionFailed",
    "CommandFailed",
    "Transport",
)


class SSHTransport:
    def __init__(self, machine):
        self._machine = machine

        ssh = SSH(machine.logger)
        ssh.register_flag_fun(machine.get_ssh_flags)
        ssh.register_host_fun(machine.get_ssh_name)
        ssh.register_passwd_fun(machine.get_ssh_password)
        ssh.privilege_escalation_command = machine.privilege_escalation_command

        self._ssh = ssh

    def reset(self) -> None:
        self._ssh.reset()

    def _get_scp_name(self) -> str:
        ssh_name = self._machine.get_ssh_name()
        # ipv6 addresses have to be wrapped in brackets for scp
        if ":" in ssh_name:
            return "[%s]" % (ssh_name)
        return ssh_name

    def _fmt_rsync_command(self, *args: str, recursive: bool = False) -> List[str]:
        master = self._ssh.get_master(user=self._machine.ssh_user)

        ssh_cmdline: List[str] = ["ssh"] + self._machine.get_ssh_flags() + master.opts
        cmdline = ["rsync", "-e", nixops.util.shlex_join(ssh_cmdline)]

        if self._machine.ssh_user != "root":
            cmdline.extend(
                [
                    "--rsync-path",
                    nixops.util.shlex_join(
                        self._ssh.privilege_escalation_command + ["rsync"]
                    ),
                ]
            )

        if recursive:
            cmdline += ["-r"]

        cmdline.extend(args)

        return cmdline

    def upload_file(self, source: str, target: str, recursive: bool = False) -> None:
        cmdline = self._fmt_rsync_command(
            source,
            self._machine.ssh_user + "@" + self._get_scp_name() + ":" + target,
            recursive=recursive,
        )
        self._machine._logged_exec(cmdline)

    def download_file(self, source: str, target: str, recursive: bool = False) -> None:
        cmdline = self._fmt_rsync_command(
            self._machine.ssh_user + "@" + self._get_scp_name() + ":" + source,
            target,
            recursive=recursive,
        )
        self._machine._logged_exec(cmdline)

    def run_command(
        self, command: Iterable[str], **kwargs
    ) -> nixops.util.ProcessResult:
        return self._ssh.run_command(command, **kwargs)

    def copy_closure(self, path: str):
        """Copy a closure to this machine."""
        ssh = self._ssh

        # Any remaining paths are copied from the local machine.
        env = dict(os.environ)
        env["NIX_SSHOPTS"] = " ".join(
            ssh._get_flags() + ssh.get_master(user=self._machine.ssh_user).opts
        )
        self._machine._logged_exec(
            [
                "nix-copy-closure",
                "--to",
                ssh._get_target(user=self._machine.ssh_user),
                path,
            ]
            + ([] if self._machine.has_fast_connection else ["--use-substitutes"]),
            env=env,
        )
