from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/ec2-rds-dbinstance.nix' % (parent_dir)

class TestEc2RdsDbinstanceTest(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestEc2RdsDbinstanceTest, self).setup()
        self.depl.nix_exprs = [ logical_spec ]

    def test_deploy(self):
        #self.depl.debug = True
        self.depl.deploy()

    # def check_command(self, command):
    #     self.depl.evaluate()
    #     resource = self.depl.resources.values()[0]
    #     return machine.run_command(command)
