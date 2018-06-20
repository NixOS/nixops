import time
from os import path

from itertools import product
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
        (
            'simple',
            [
                '{}/ec2-rds-dbinstance.nix'.format(parent_dir),
            ]
        ),
        # This test with database security group can only be run on aws account,
        # that supports EC2-Classic platform.
        # (https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.FindDefaultVPC.html)
        # These accounts are legacy and are not created after 2013.

        # If your account doesn't support EC2-Classic, you will get an error:
        # `VPC DB Security Groups cannot be modified with this API version.
        # Please use an API version between 2012-01-15 and 2012-10-31 to modify this group.`
        # TODO: remove it?
        # (
        #     'sg',
        #     [
        #         '{}/ec2-rds-dbinstance-with-sg.nix'.format(parent_dir),
        #     ]
        # )
    ],
))
def test_ec2_rds_dbinstance(state_extension, nix_expressions_tuple):
    nix_expressions_id, nix_expressions = nix_expressions_tuple

    with using_unique_state_file(
            [test_ec2_rds_dbinstance.__name__, nix_expressions_id],
            state_extension
        ) as state:
        deployment = create_deployment(state, nix_expressions)
        deployment.deploy()
