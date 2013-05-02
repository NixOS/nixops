import os
import subprocess
from nixops import deployment

from tests.functional import DatabaseUsingTest

class GenericDeploymentTest(DatabaseUsingTest):
    def setup(self):
        super(GenericDeploymentTest,self).setup()
        self.depl = deployment.create_deployment(self.db)
        self.depl.auto_response = "y"

    def set_ec2_args(self):
        assert os.getenv("EC2_SECURITY_GROUP") is not None, "The EC2_SECURITY_GROUP env var must be set to the name of an ec2 security group with inbound ssh access"
        assert os.getenv("EC2_KEY_PAIR") is not None, "The EC2_KEY_PAIR env var must be set to the name of an ec2 keypair"
        assert os.getenv("EC2_PRIVATE_KEY_FILE") is not None, "The EC2_PRIVATE_KEY_FILE env var must be set to the private key of an ec2 keypair"

        self.depl.set_argstr("securityGroup", os.getenv("EC2_SECURITY_GROUP"))
        self.depl.set_argstr("keyPair", os.getenv("EC2_KEY_PAIR"))
        self.depl.set_argstr("privateKey", os.getenv("EC2_PRIVATE_KEY_FILE"))
