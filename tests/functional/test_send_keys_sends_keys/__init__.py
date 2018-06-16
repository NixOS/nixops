from nose import tools
from nixops.ssh_util import SSHCommandFailed
from nixops.util import root_dir
from itertools import product
from parameterized import parameterized
from os import path

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_unique_state_file import using_unique_state_file

parent_dir = path.dirname(__file__)

secret_key_spec    = '{}/secret_key.nix'.format(parent_dir)
elsewhere_key_spec = '{}/elsewhere_key.nix'.format(parent_dir)

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
            'libvirtd',
            [
                '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
                '{}/tests/functional/shared/nix_expressions/libvirtd_base.nix'.format(root_dir),
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
        )
    ],
))
def test_send_keys_sends_keys(state_extension, nix_expressions_tuple):
    nix_expressions_id, nix_expressions = nix_expressions_tuple

    with using_unique_state_file(
            [test_send_keys_sends_keys.__name__, nix_expressions_id],
            state_extension
        ) as state:
        nix_expressions_ = nix_expressions + [ secret_key_spec, elsewhere_key_spec ]

        deployment = create_deployment(state, nix_expressions_)
        deployment.deploy()

        deployment_run_command(deployment, "test -f /run/keys/secret.key")
        deployment_run_command(deployment, "rm -f /run/keys/secret.key")
        deployment_run_command(deployment, "test -f /new/directory/elsewhere.key")
        deployment_run_command(deployment, "rm -f /new/directory/elsewhere.key")

        deployment.send_keys()

        deployment_run_command(deployment, "test -f /run/keys/secret.key")
        deployment_run_command(deployment, "test -f /new/directory/elsewhere.key")
