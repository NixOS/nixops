from nose import tools
from itertools import product
from os import path
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_unique_state_file import using_unique_state_file

parent_dir = path.dirname(__file__)

@parameterized(product(
    [
        'json',
        'nixops'
    ],
    [
        [
            '{}/invalid-identifier.nix'.format(parent_dir),
        ]
    ]
))
def test_invalid_indentifier(state_extension, nix_expressions):
    with using_unique_state_file(
            [test_invalid_indentifier.__name__],
            state_extension
        ) as state:
        deployment = create_deployment(state, nix_expressions)
        with tools.assert_raises(Exception):
            deployment.evaluate()
