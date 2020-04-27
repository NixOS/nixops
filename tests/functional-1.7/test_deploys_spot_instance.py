from nose import tools
from tests.functional import single_machine_test
from os import path

parent_dir = path.dirname(__file__)


class TestDeploysSpotInstance(single_machine_test.SingleMachineTest):
    def run_check(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [
            "%s/single_machine_ec2_spot_instance.nix" % (parent_dir),
        ]
        self.depl.deploy()
        self.check_command("test -f /etc/NIXOS")
