from os import path
from nose import tools

from tests.functional import single_machine_test

parent_dir = path.dirname(__file__)

secret_key_spec = '%s/single_machine_secret_key.nix' % (parent_dir)

class TestSendKeysSendsKeys(single_machine_test.SingleMachineTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestSendKeysSendsKeys,self).setup()
        self.depl.nix_exprs = self.depl.nix_exprs + [ secret_key_spec ]

    def run_check(self):
        self.depl.deploy()
        tools.assert_true(self.check_command("test -f /run/keys/secret.key"))
        tools.assert_true(self.check_command("rm -f /run/keys/secret.key"))
        self.depl.send_keys()
        tools.assert_true(self.check_command("test -f /run/keys/secret.key"))
