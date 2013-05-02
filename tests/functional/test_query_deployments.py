from nixops import deployment
from nose import tools

from tests.functional import DatabaseUsingTest

class TestQueryDeployments(DatabaseUsingTest):
    def test_shows_all_deployments(self):
        depls = []
        for i in range(10):
            depls.append(deployment.create_deployment(self.db))
        uuids = deployment.query_deployments(self.db)
        for depl in depls:
            tools.assert_true(any([ depl.uuid == uuid for uuid in uuids ]))
