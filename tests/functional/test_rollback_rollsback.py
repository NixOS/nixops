from os import path
from nose import tools

from tests.functional import single_machine_test

from nixops.ssh_util import SSHCommandFailed

from nixops.evaluation import NetworkFile

parent_dir = path.dirname(__file__)

has_hello_spec = "%s/single_machine_has_hello.nix" % (parent_dir)

rollback_spec = "%s/single_machine_rollback.nix" % (parent_dir)


class TestRollbackRollsback(single_machine_test.SingleMachineTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestRollbackRollsback, self).setup()
        self.depl.network_expr = NetworkFile(rollback_spec)
        self.depl.nix_exprs = self.depl.nix_exprs + [rollback_spec]

    def run_check(self):
        self.depl.deploy()
        with tools.assert_raises(SSHCommandFailed):
            self.check_command("hello")
        self.depl.network_expr = NetworkFile(has_hello_spec)
        self.depl.deploy()
        self.check_command("hello")
        self.depl.rollback(generation=1)
        with tools.assert_raises(SSHCommandFailed):
            self.check_command("hello")
