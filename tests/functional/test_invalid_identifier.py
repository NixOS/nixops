from os import path

from nose import tools
from nose.tools import raises
from tests.functional import generic_deployment_test

from nixops.evaluation import NetworkFile


parent_dir = path.dirname(__file__)

logical_spec = "%s/invalid-identifier.nix" % (parent_dir)


class TestInvalidIdentifier(generic_deployment_test.GenericDeploymentTest):
    def setup(self):
        super(TestInvalidIdentifier, self).setup()
        self.depl.network_expr = NetworkFile(logical_spec)

    @raises(Exception)
    def test_invalid_identifier_fails_evaluation(self):
        self.depl.evaluate()
