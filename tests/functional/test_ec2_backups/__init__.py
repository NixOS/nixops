import time

from nixops.util import root_dir
from itertools import product
from nose.tools import with_setup
from parameterized import parameterized

from tests.functional.shared.deployment_run_command import deployment_run_command
from tests.functional.shared.create_deployment import create_deployment
from tests.functional.shared.using_state_file import using_state_file

@parameterized(product(
    ['json', 'nixops'],
    [
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_ebs.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_base.nix'.format(root_dir)
        ]
    ],
))
def test_ec2_backups_simple(state_extension, nix_expressions):
    with using_state_file(
            unique_name='test_ec2_backups',
            state_extension=state_extension) as state:
        deployment = create_deployment(state, nix_expressions)
        backup_and_restore_path(deployment)

@parameterized(product(
    ['json', 'nixops'],
    [
        [
            '{}/tests/functional/shared/nix_expressions/logical_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_ebs.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_base.nix'.format(root_dir),
            '{}/tests/functional/shared/nix_expressions/ec2_raid-0.nix'.format(root_dir)
        ]
    ],
))
def test_ec2_backups_raid(state_extension, nix_expressions):
    with using_state_file(
            unique_name='test_ec2_backups',
            state_extension=state_extension) as state:
        deployment = create_deployment(state, nix_expressions)
        backup_and_restore_path(deployment, '/data')

def backup_and_restore_path(deployment, path=""):
    deployment.deploy()
    deployment_run_command(deployment, "echo -n important-data > {}/back-me-up".format(path))
    backup_id = deployment.backup()
    backups = deployment.get_backups()
    while backups[backup_id]['status'] == "running":
        time.sleep(10)
        backups = deployment.get_backups()
    deployment_run_command(deployment, "rm {}/back-me-up".format(path))
    deployment.restore(backup_id=backup_id)
    deployment_run_command(deployment, "echo -n important-data | diff {}/back-me-up -".format(path))
