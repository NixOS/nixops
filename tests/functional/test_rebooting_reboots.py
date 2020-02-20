from nose import tools

from tests.functional import single_machine_test

from nixops.ssh_util import SSHCommandFailed


class TestRebootingReboots(single_machine_test.SingleMachineTest):
    def run_check(self):
        self.depl.deploy()
        self.check_command("touch /run/not-rebooted")
        self.depl.reboot_machines(wait=True)
        m = list(self.depl.active.values())[0]
        m.check()
        tools.assert_equal(m.state, m.UP)
        with tools.assert_raises(SSHCommandFailed):
            self.check_command("test -f /run/not-rebooted")
