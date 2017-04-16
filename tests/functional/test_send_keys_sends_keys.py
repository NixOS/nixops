from os import path
from nose import tools

from tests.functional import single_machine_test

parent_dir = path.dirname(__file__)

secret_key_ram_spec = '%s/single_machine_secret_key_ram.nix' % (parent_dir)
secret_key_disk_spec = '%s/single_machine_secret_key_disk.nix' % (parent_dir)

class TestSendKeysSendsKeys(single_machine_test.SingleMachineTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestSendKeysSendsKeys,self).setup()

    def run_check(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [ secret_key_ram_spec ]

        self.depl.deploy()
        self.check_command("test -f /run/keys/secret.key")
        self.check_command("rm -f /run/keys/secret.key")
        self.depl.send_keys()
        self.check_command("test -f /run/keys/secret.key")

    def run_check(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [ secret_key_disk_spec ]

        self.depl.deploy()
        self.check_command("test -f /run/keys/secret.key")
        self.check_command("rm -f /run/keys/secret.key")
        self.depl.send_keys()
        self.check_command("test -f /run/keys/secret.key")
