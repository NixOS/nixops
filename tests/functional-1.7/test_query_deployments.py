from nose import tools

from tests.functional import DatabaseUsingTest


class TestQueryDeployments(DatabaseUsingTest):
    def test_shows_all_deployments(self):
        depls = []
        for i in range(10):
            depls.append(self.sf.create_deployment())
        uuids = self.sf.query_deployments()
        for depl in depls:
            tools.assert_true(any([depl.uuid == uuid for uuid in uuids]))
