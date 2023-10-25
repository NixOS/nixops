from os import path

from pytest import raises
from tests.functional.generic_deployment_test import GenericDeploymentTest

from nixops.evaluation import NetworkFile


parent_dir = path.dirname(__file__)

logical_spec = "%s/invalid-identifier.nix" % (parent_dir)


class TestInvalidIdentifier(GenericDeploymentTest):
    def setup_method(self):
        super(TestInvalidIdentifier, self).setup_method()
        self.depl.network_expr = NetworkFile(logical_spec)

    def test_invalid_identifier_fails_evaluation(self):
        with raises(Exception):
            self.depl.evaluate()
