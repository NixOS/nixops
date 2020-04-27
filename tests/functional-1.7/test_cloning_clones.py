from nose import tools

from tests.functional import single_machine_test


class TestCloningClones(single_machine_test.SingleMachineTest):
    def run_check(self):
        depl = self.depl.clone()
        tools.assert_equal(depl.nix_exprs, self.depl.nix_exprs)
        tools.assert_equal(depl.nix_path, self.depl.nix_path)
        tools.assert_equal(depl.args, self.depl.args)
