from os import path
from nose import tools

from tests.functional import single_machine_test

parent_dir = path.dirname(__file__)

output_spec    = '%s/single_machine_outputs.nix'    % (parent_dir)

class TestOutputCreates(single_machine_test.SingleMachineTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestOutputCreates,self).setup()
        self.depl.nix_exprs = self.depl.nix_exprs + [ output_spec ]

    def run_check(self):
        self.depl.deploy()
        self.check_command("test -f /run/keys/secret.key")
        self.check_command("rm -f /run/keys/secret.key")
        self.depl.send_keys()
        self.check_command("test -f /run/keys/secret.key")
        assert "\"12345\"" == self.depl.machines["machine"].run_command("cat /run/keys/secret.key",capture_stdout=True), "Key contents incorrect"
