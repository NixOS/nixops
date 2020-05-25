from typing import List
import shlex


def format_command(
    command: str,
    user: str,
    allow_ssh_args: bool,
    privilege_escalation_command: List[str],
) -> List[str]:
    if allow_ssh_args:
        return shlex.split(command)

    # Don't make assumptions about remote login shell
    cmd: List[str] = ["bash", "-c", command]

    if user and user != "root":
        cmd = privilege_escalation_command + cmd

    return cmd
