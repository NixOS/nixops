from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

@parameterized(product(
    ['json', 'nixops'],
    [
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_spot_instance.nix'.format(root_dir)
        ]
    ],
))

def test_ec2_spot_instance(state_extension, nix_expressions):
    with using_state_file(state_extension) as state:
        deployment = create_deployment(state, nix_expressions)
        deployment_run_command(deployment, "test -f /etc/NIXOS")
