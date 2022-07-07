from tests.functional.single_machine_test import SingleMachineTest


class TestCloningClones(SingleMachineTest):
    def run_check(self):
        depl = self.depl.clone()
        assert depl.network_expr.network == self.depl.network_expr.network
        assert depl.nix_path == self.depl.nix_path
        assert depl.args == self.depl.args
