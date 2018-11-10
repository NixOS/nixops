from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_unique_state_file import using_unique_state_file
from tests.functional.test_ec2_backups.helpers import backup_and_restore_path

@parameterized(product(
    [
        'json',
        'nixops'
    ],
    [
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_ebs.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_base.nix'.format(root_dir)
        ]
    ],
))
def test_ec2_backups_simple_xd(state_extension, nix_expressions):
    with using_unique_state_file(
            [test_ec2_backups_simple_xd.__name__],
            state_extension
        ) as state:
        deployment = create_deployment(state, nix_expressions)
        backup_and_restore_path(deployment)
