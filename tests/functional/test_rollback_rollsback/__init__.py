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

has_hello_spec = '{}/has_hello.nix'.format(parent_dir)
rollback_spec  = '{}/rollback.nix'.format(parent_dir)

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
def test_rollback_rollsback(state_extension, nix_expressions_tuple):
    nix_expressions_id, nix_expressions = nix_expressions_tuple

    with using_unique_state_file(
            [test_rollback_rollsback.__name__, nix_expressions_id],
            state_extension
        ) as state:
        nix_expressions_ = nix_expressions + [ rollback_spec ]

        deployment = create_deployment(state)
        deployment.nix_exprs = nix_expressions_
        deployment.deploy()

        with tools.assert_raises(SSHCommandFailed):
            deployment_run_command(deployment, "hello")

        nix_expressions__ = nix_expressions + [ rollback_spec, has_hello_spec ]

        deployment.nix_exprs = nix_expressions__
        deployment.deploy()

        deployment_run_command(deployment, "hello")

        deployment.rollback(generation=1)

        with tools.assert_raises(SSHCommandFailed):
            deployment_run_command(deployment, "hello")
