from os import path

from tests.functional.generic_deployment_test import GenericDeploymentTest

from nixops.evaluation import NetworkFile

parent_dir = path.dirname(__file__)

ssh_key_pair_spec = "%s/ssh-key-pair-resource.nix" % (parent_dir)


class TestSSHKeyPairResource(GenericDeploymentTest):
    def setup_method(self):
        super(TestSSHKeyPairResource, self).setup_method()
        self.depl.network_expr = NetworkFile(ssh_key_pair_spec)

    def test_evaluate(self):
        self.depl.evaluate()

        assert self.depl.definitions and "ssh-key" in self.depl.definitions
