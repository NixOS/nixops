from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/single_machine_logical_base.nix' % (parent_dir)

class TestStoppingStops(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestStoppingStops,self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def check_stopping(self):
        self.depl.deploy()
        self.depl.stop_machines()
        m = self.depl.active.values()[0]
        m.check()
        tools.assert_equal(m.state, m.STOPPED)

    def test_ec2(self):
        self.set_ec2_args()
        self.depl.nix_exprs = self.depl.nix_exprs + [
            ('%s/single_machine_ec2_base.nix' % (parent_dir))
        ]
        self.check_stopping()
