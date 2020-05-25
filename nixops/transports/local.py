from nixops.command import format_command
from nixops.backends import MachineState
from typing import List
import nixops.util
import getpass


def _fmt_cp(
    machine: MachineState, source: str, target: str, recursive: bool = False
) -> List[str]:
    cmd: List[str] = ["cp"]
    if recursive:
        cmd.append("-r")
    cmd.extend([source, target])

    return format_command(
        nixops.util.shlex_join(cmd),
        user=getpass.getuser(),
        allow_ssh_args=False,
        privilege_escalation_command=machine.privilege_escalation_command,
    )


class LocalTransport:
    def __init__(self, machine: MachineState):
        self._machine = machine

    def reset(self) -> None:
        pass

    def upload_file(self, source: str, target: str, recursive: bool = False) -> None:
        self.run_command(
            _fmt_cp(self._machine, source, target, recursive), user=getpass.getuser()
        )

    def download_file(self, source: str, target: str, recursive: bool = False) -> None:
        self.run_command(
            _fmt_cp(self._machine, source, target, recursive), user=getpass.getuser()
        )

    def run_command(
        self,
        command: List[str],
        user: str,
        capture_stdout: bool = False,
        check: bool = False,
    ) -> nixops.util.ProcessResult:
        return nixops.util.logged_exec(
            command,
            logger=self._machine.logger,
            capture_stdout=capture_stdout,
            check=check,
        )

    def copy_closure(self, path: str) -> None:
        # copy_closure is a no-op on localhost
        pass
