import time

from tests.functional.shared.deployment_run_command import deployment_run_command

def backup_and_restore_path(deployment, path=""):
    deployment.deploy()
    deployment_run_command(deployment, "printf 'important-data' > {}/back-me-up".format(path))
    backup_id = deployment.backup()
    backups = deployment.get_backups()
    while backups[backup_id]['status'] == "running":
        time.sleep(10)
        backups = deployment.get_backups()
    deployment_run_command(deployment, "rm {}/back-me-up".format(path))
    deployment.restore(backup_id=backup_id)
    deployment_run_command(deployment, "printf 'important-data' | diff {}/back-me-up -".format(path))
