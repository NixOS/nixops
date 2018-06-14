import time
from os import path

from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

parent_dir = path.dirname(__file__)

@parameterized(product(
    ['json', 'nixops'],
    [
        [
            '{}/ec2-rds-dbinstance.nix'.format(parent_dir),
        ],
        [
            '{}/ec2-rds-dbinstance.nix'.format(parent_dir),
            '{}/ec2-rds-dbinstance-with-sg.nix'.format(parent_dir),
        ]
    ],
))
def test_ec2_rds_dbinstance(state_extension, nix_expressions):
    with using_state_file(state_extension) as state:
        deployment = create_deployment(state, nix_expressions)
        deployment.deploy()
