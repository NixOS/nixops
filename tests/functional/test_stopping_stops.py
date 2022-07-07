from tests.functional import single_machine_test


class TestStoppingStops(single_machine_test.SingleMachineTest):
    def run_check(self):
        self.depl.deploy()
        self.depl.stop_machines()
        m = list(self.depl.active.values())[0]
        assert m.state == m.STOPPED
