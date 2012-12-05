from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/deploys_nixos_logical.nix' % (parent_dir)

class TestDeploysNixos(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestDeploysNixos,self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def check_for_nixos(self):
        tools.assert_true(self.check_command("test -f /etc/NIXOS"))

    def test_ec2(self):
        self.set_ec2_args()
        self.depl.nix_exprs = self.depl.nix_exprs + [
            ('%s/deploys_nixos_ec2.nix' % (parent_dir))
        ]
        self.depl.deploy()
        self.check_for_nixos()
