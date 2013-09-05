import os
import subprocess
import nixops.statefile

from nose import SkipTest

from tests.functional import DatabaseUsingTest

class GenericDeploymentTest(DatabaseUsingTest):
    def setup(self):
        super(GenericDeploymentTest,self).setup()
        self.depl = self.sf.create_deployment()
        self.depl.logger.set_autoresponse("y")

    def set_ec2_args(self):
        if os.getenv("EC2_SECURITY_GROUP") is None:
            raise SkipTest("The EC2_SECURITY_GROUP env var must be set to the"
                           " name of an EC2 security group with inbound ssh"
                           " access")

        self.depl.set_argstr("securityGroup", os.getenv("EC2_SECURITY_GROUP"))
