from nixops.util import root_dir
from itertools import product
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
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
            '{}/tests/functional/shared/nix_expressions/ec2_base_nvme.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_raid-0-nvme.nix'.format(root_dir)
        ]
    ],
))
def test_ec2_backups_raid_nvme(state_extension, nix_expressions):
    with using_unique_state_file(
            [test_ec2_backups_raid_nvme.__name__],
            state_extension
        ) as state:
        deployment = create_deployment(state, nix_expressions)
        backup_and_restore_path(deployment, '/data')
        deployment_run_command(deployment, "mount | grep '/dev/mapper/raid-raid on /data type ext4'")
        deployment_run_command(deployment, "mount | grep '/dev/nvme0n1p1 on /'")
