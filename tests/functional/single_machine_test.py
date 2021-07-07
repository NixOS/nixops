from os import path

from nose import tools
from nose.plugins.attrib import attr

from tests.functional import generic_deployment_test

from nixops.evaluation import NetworkFile

parent_dir = path.dirname(__file__)

logical_spec = "{0}/single_machine_logical_base.nix".format(parent_dir)


class SingleMachineTest(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(SingleMachineTest, self).setup()
        self.depl.network_expr = NetworkFile(logical_spec)

    def check_command(self, command):
        self.depl.evaluate()
        machine = next(iter(self.depl.machines.values()))
        return machine.run_command(command)
