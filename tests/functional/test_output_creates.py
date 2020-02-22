from os import path
from nose import tools
from nose.plugins.attrib import attr

from tests.functional import single_machine_test
from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

output_spec = "%s/single_machine_outputs.nix" % (parent_dir)


@attr("libvirtd")
class TestOutputCreates(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestOutputCreates, self).setup()
        self.depl.nix_exprs = self.depl.nix_exprs + [output_spec]

    def test_deploy(self):
        self.depl.deploy()
        assert '"12345"' == self.depl.machines["machine"].run_command(
            "cat /etc/test.txt", capture_stdout=True
        ), "Resource contents incorrect"

    def test_update(self):
        self.depl.deploy()
        assert '"12345"' == self.depl.machines["machine"].run_command(
            "cat /etc/test.txt", capture_stdout=True
        ), "Resource contents incorrect"

        self.depl.nix_exprs = self.depl.nix_exprs + [
            "%s/single_machine_outputs_mod.nix" % (parent_dir)
        ]
        self.depl.deploy()
        assert '"123456"' == self.depl.machines["machine"].run_command(
            "cat /etc/test.txt", capture_stdout=True
        ), "Resource contents update incorrect"
