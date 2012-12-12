from charon import deployment
from nose import tools

from tests.functional import db

class TestQueryDeployments(object):
    def test_shows_all_deployments(self):
        database = db()
        depls = []
        for i in range(10):
            depls.append(deployment.create_deployment(database))
        uuids = deployment.query_deployments(database)
        for depl in depls:
            tools.assert_true(any([ depl.uuid == uuid for uuid in uuids ]))
