from nose import tools
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

@parameterized(
    ['json', 'nixops']
)
def test_query_deployments(state_extension):
    with using_state_file(state_extension) as state:
        deployments = []

        for i in range(10):
            deployments.append(state.create_deployment())

        uuids = state.query_deployments()

        for depl in deployments:
            tools.assert_true(any([ depl.uuid == uuid for uuid in uuids ]))
