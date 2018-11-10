from os import path

from nose import tools
from nixops.util import root_dir
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
            'ec2',
            [
                '{}/ec2_with_nvme_device_mapping.nix'.format(parent_dir)
            ],
        )
    ],
))

def test_ec2_with_nvme_device_mapping(state_extension, nix_expressions_tuple):
    nix_expressions_id, nix_expressions = nix_expressions_tuple

    with using_unique_state_file(
            [test_ec2_with_nvme_device_mapping.__name__, nix_expressions_id],
            state_extension
        ) as state:
        deployment = create_deployment(state, nix_expressions)
        deployment.deploy()
        deployment_run_command(deployment, "test -f /etc/NIXOS")
        deployment_run_command(deployment, "lsblk | grep nvme1n1")
        deployment_run_command(deployment, "cat /proc/mounts | grep '/dev/nvme1n1 /data ext4 rw,relatime,data=ordered 0 0'")
        deployment_run_command(deployment, "touch /data/asdf")
