from os import path

from tests.functional.single_machine_test import SingleMachineTest

parent_dir = path.dirname(__file__)

secret_key_spec = "%s/single_machine_secret_key.nix" % (parent_dir)
elsewhere_key_spec = "%s/single_machine_elsewhere_key.nix" % (parent_dir)


class TestSendKeysSendsKeys(SingleMachineTest):
    _multiprocess_can_split_ = True

    def setup_method(self):
        super(TestSendKeysSendsKeys, self).setup_method()
        self.depl.nix_exprs = self.depl.nix_exprs + [
            secret_key_spec,
            elsewhere_key_spec,
        ]

    def run_check(self):
        self.depl.deploy()
        self.check_command("test -f /run/keys/secret.key")
        self.check_command("rm -f /run/keys/secret.key")
        self.check_command("test -f /new/directory/elsewhere.key")
        self.check_command("rm -f /new/directory/elsewhere.key")
        self.depl.send_keys()
        self.check_command("test -f /run/keys/secret.key")
        self.check_command("test -f /new/directory/elsewhere.key")
