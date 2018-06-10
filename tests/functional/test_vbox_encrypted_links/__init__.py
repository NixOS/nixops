from os import path
from nose import tools, SkipTest
from tests.functional import generic_deployment_test
from nixops.ssh_util import SSHCommandFailed
from nixops.util import devnull
import sys
import time
import signal
import subprocess

parent_dir = path.dirname(__file__)

logical_spec = '%s/encrypted-links.nix' % (parent_dir)

class TestEncryptedLinks(generic_deployment_test.GenericDeploymentTest):

    def setup(self):
        super(TestEncryptedLinks,self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def test_deploy(self):
        if subprocess.call(["VBoxManage", "--version"],
                           stdout=devnull,
                           stderr=devnull) != 0:
            raise SkipTest("VirtualBox is not available")

        self.depl.debug = True
        self.depl.deploy()

        # !!! Shouldn't need this, instead the encrypted links target
        # should wait until the link is active...
        time.sleep(1)
        self.ping("machine1", "machine2")
        self.ping("machine2", "machine1")
        self.depl.machines["machine1"].run_command("systemctl stop encrypted-links.target")
        with tools.assert_raises(SSHCommandFailed):
            self.ping("machine1", "machine2")
        with tools.assert_raises(SSHCommandFailed):
            self.ping("machine2", "machine1")

    def ping(self, machine1, machine2):
        self.depl.machines[machine1].run_command("ping -c1 {0}-encrypted".format(machine2))
