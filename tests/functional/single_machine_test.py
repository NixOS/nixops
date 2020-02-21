from os import path

from nose import tools
from nose.plugins.attrib import attr

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = "{0}/single_machine_logical_base.nix".format(parent_dir)


class SingleMachineTest(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(SingleMachineTest, self).setup()
        self.depl.nix_exprs = [logical_spec]

    @attr("ec2")
    def test_ec2(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [
            ("{0}/single_machine_ec2_base.nix".format(parent_dir))
        ]
        self.run_check()

    @attr("gce")
    def test_gce(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [
            ("{0}/single_machine_gce_base.nix".format(parent_dir))
        ]
        self.run_check()

    @attr("azure")
    def test_azure(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [
            ("{0}/single_machine_azure_base.nix".format(parent_dir))
        ]
        self.run_check()

    @attr("libvirtd")
    def test_libvirtd(self):
        self.depl.nix_exprs = self.depl.nix_exprs + [
            ("{0}/single_machine_libvirtd_base.nix".format(parent_dir))
        ]
        self.run_check()

    def check_command(self, command):
        self.depl.evaluate()
        machine = next(iter(self.depl.machines.values()))
        return machine.run_command(command)
