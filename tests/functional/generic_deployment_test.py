import os
import subprocess

from nose import SkipTest

from tests.functional import DatabaseUsingTest

class GenericDeploymentTest(DatabaseUsingTest):
    def setup(self):
        super(GenericDeploymentTest,self).setup()
        self.depl = self.sf.create_deployment()
        self.depl.logger.set_autoresponse("y")
