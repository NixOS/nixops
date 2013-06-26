from os import path
from nose import tools
from tests.functional import generic_deployment_test
from nixops import backends
import time

parent_dir = path.dirname(__file__)

logical_spec = '%s/encrypted-links.nix' % (parent_dir)

class TestEncryptedLinks(generic_deployment_test.GenericDeploymentTest):

    def setup(self):
        super(TestEncryptedLinks,self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def test_deploy(self):
        self.depl.debug = True
        self.depl.deploy()

        # !!! Shouldn't need this, instead the encrypted links target
        # should wait until the link is active...
        time.sleep(1)
        self.ping("machine1", "machine2")
        self.ping("machine2", "machine1")
        self.depl.machines["machine1"].run_command("systemctl stop encrypted-links.target")
        with tools.assert_raises(backends.SSHCommandFailed):
            self.ping("machine1", "machine2")
        with tools.assert_raises(backends.SSHCommandFailed):
            self.ping("machine2", "machine1")

    def ping(self, machine1, machine2):
        self.depl.machines[machine1].run_command("ping -c1 {0}-encrypted".format(machine2))
