from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/ec2-security-groups.nix' % (parent_dir)

class TestEc2SecurityGroupsTest(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestEc2SecurityGroupsTest, self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def test_deploy(self):
        self.depl.deploy()
