from nose import tools

from tests.functional import single_machine_test


class TestStartingStarts(single_machine_test.SingleMachineTest):
    def run_check(self):
        self.depl.deploy()
        self.depl.stop_machines()
        self.depl.start_machines()
        m = list(self.depl.active.values())[0]
        m.check()
        tools.assert_equal(m.state, m.UP)
