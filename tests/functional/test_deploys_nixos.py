from tests.functional import single_machine_test

class TestDeploysNixos(single_machine_test.SingleMachineTest):
    def run_check(self):
        self.depl.deploy()
        self.check_command("test -f /etc/NIXOS")
