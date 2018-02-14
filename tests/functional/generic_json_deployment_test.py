import os
import subprocess

from nose import SkipTest

from tests.functional import JSONUsingTest

class GenericJsonDeploymentTest(JSONUsingTest):
    def setup(self):
        super(GenericJsonDeploymentTest,self).setup()
        self.depl = self.sf.create_deployment()
        self.depl.logger.set_autoresponse("y")
