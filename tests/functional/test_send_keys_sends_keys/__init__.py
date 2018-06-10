from nose import tools
from nixops.ssh_util import SSHCommandFailed
from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

secret_key_spec    = '{}/tests/functional/shared/nix_expressions/single_machine_secret_key.nix'.format(root_dir)
elsewhere_key_spec = '{}/tests/functional/shared/nix_expressions/single_machine_elsewhere_key.nix'.format(root_dir)

@parameterized(product(
    ['json', 'nixops'],
    [
        # vbox
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/vbox_base.nix'.format(root_dir),
        ],
        # ec2
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_base.nix'.format(root_dir),
        ],
        # gce
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/gce_base.nix'.format(root_dir),
        ],
        # azure
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/azure_base.nix'.format(root_dir),
        ],
        # libvirtd
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/libvirtd_base.nix'.format(root_dir),
        ]
    ],
))
def test_send_keys_sends_keys(state_extension, nix_expressions):
    with using_state_file(state_extension) as state:
        deployment = create_deployment(state, nix_expressions)

        deployment.nix_exprs = deployment.nix_exprs + [ secret_key_spec, elsewhere_key_spec ]
        deployment.deploy()

        deployment_run_command(deployment, "test -f /run/keys/secret.key")
        deployment_run_command(deployment, "rm -f /run/keys/secret.key")
        deployment_run_command(deployment, "test -f /new/directory/elsewhere.key")
        deployment_run_command(deployment, "rm -f /new/directory/elsewhere.key")
        deployment.send_keys()
        deployment_run_command(deployment, "test -f /run/keys/secret.key")
        deployment_run_command(deployment, "test -f /new/directory/elsewhere.key")
