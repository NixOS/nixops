from nose import tools
from nixops.ssh_util import SSHCommandFailed
from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

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
def test_rebooting_reboots(state_extension, nix_expressions):
    with using_state_file(state_extension) as state:
        deployment = create_deployment(state, nix_expressions)
        deployment.deploy()
        deployment_run_command(deployment, "touch /run/not-rebooted")
        deployment.reboot_machines(wait=True)
        m = deployment.active.values()[0]
        m.check()
        tools.assert_equal(m.state, m.UP)
        with tools.assert_raises(SSHCommandFailed):
            deployment_run_command(deployment, "test -f /run/not-rebooted")
