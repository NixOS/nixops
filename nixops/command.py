from typing import Iterable
from typing import Union
from typing import List
import nixops.util
import shlex


Command = Union[str, Iterable[str]]


def format_command(
    command: Command,
    user: str,
    allow_ssh_args: bool,
    privilege_escalation_command: List[str],
) -> Iterable[str]:
    # Don't make assumptions about remote login shell
    cmd: List[str] = ["bash", "-c"]

    if isinstance(command, str):
        if allow_ssh_args:
            return shlex.split(command)
        else:
            cmd.append(command)
    # iterable
    elif allow_ssh_args:
        return command
    else:
        cmd.append(
            " ".join(["'{0}'".format(arg.replace("'", r"'\''")) for arg in command])
        )

    if user and user != "root":
        cmd = privilege_escalation_command + cmd

    return ["--", nixops.util.shlex_join(cmd)]
