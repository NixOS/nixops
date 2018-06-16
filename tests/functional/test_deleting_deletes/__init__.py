from nose import tools
from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_unique_state_file import using_unique_state_file

@parameterized(product(
    [
        'json',
        'nixops'
    ],
    [
        (
            'vbox',
            [
                '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
                '{}/tests/functional/shared/nix_expressions/vbox_base.nix'.format(root_dir),
            ]
        ),
        (
            'ec2',
            [
                '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
                '{}/tests/functional/shared/nix_expressions/ec2_base.nix'.format(root_dir),
            ],
        ),
        (
            'gce',
            [
                '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
                '{}/tests/functional/shared/nix_expressions/gce_base.nix'.format(root_dir),
            ],
        ),
        (
            'azure',
            [
                '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
                '{}/tests/functional/shared/nix_expressions/azure_base.nix'.format(root_dir),
            ],
        ),
        (
            'libvirtd',
            [
                '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
                '{}/tests/functional/shared/nix_expressions/libvirtd_base.nix'.format(root_dir),
            ]
        )
    ],
))

def test_deleting_deletes(state_extension, nix_expressions_tuple):
    nix_expressions_id, nix_expressions = nix_expressions_tuple

    with using_unique_state_file(
            [test_deleting_deletes.__name__, nix_expressions_id],
            state_extension
        ) as state:
        deployment = create_deployment(state, nix_expressions)

        uuid = deployment.uuid
        deployment.delete()
        tools.assert_raises(Exception, state.open_deployment, (uuid,))
