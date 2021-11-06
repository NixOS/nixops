from tests.functional.single_machine_test import SingleMachineTest


class TestDeploysNixos(SingleMachineTest):
    def run_check(self):
        self.depl.deploy()
        self.check_command("test -f /etc/NIXOS")
