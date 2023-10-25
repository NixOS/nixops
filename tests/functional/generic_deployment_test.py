from tests.functional import DatabaseUsingTest


class GenericDeploymentTest(DatabaseUsingTest):
    def setup_method(self):
        super(GenericDeploymentTest, self).setup_method()
        self.depl = self.sf.create_deployment()
        self.depl.logger.set_autoresponse("y")
