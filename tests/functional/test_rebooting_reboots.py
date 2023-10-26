from pytest import raises

from tests.functional.single_machine_test import SingleMachineTest

from nixops.ssh_util import SSHCommandFailed


class TestRebootingReboots(SingleMachineTest):
    def run_check(self):
        self.depl.deploy()
        self.check_command("touch /run/not-rebooted")
        self.depl.reboot_machines(wait=True)
        assert self.depl.active
        m = list(self.depl.active.values())[0]
        m.check()
        assert m.state == m.UP
        with raises(SSHCommandFailed):
            self.check_command("test -f /run/not-rebooted")
