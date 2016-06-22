from os import path
from nose import tools
from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/ec2-security-groups.nix' % (parent_dir)

class TestEc2SecurityGroups(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestEc2SecurityGroups, self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def test_deploy(self):
        self.depl.debug = True
        self.depl.deploy()

        self.depl.machines["client1"].run_command("curl server")

        with tools.assert_raises(SSHCommandFailed):
            self.depl.machines["client2"].run_command("curl server")
