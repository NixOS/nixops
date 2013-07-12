import time

from os import path

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/single_machine_logical_base.nix' % (parent_dir)


class TestBackups(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestBackups, self).setup()
        self.set_ec2_args()
        self.depl.nix_exprs = [
            logical_spec,
            '%s/single_machine_ec2_ebs.nix' % (parent_dir),
            '%s/single_machine_ec2_base.nix' % (parent_dir)
        ]

    def backup_and_restore_path(self, path=""):
        self.depl.deploy()
        self.check_command("echo -n important-data > %s/back-me-up" % (path))
        backup_id = self.depl.backup()
        backups = self.depl.get_backups()
        while backups[backup_id]['status'] == "running":
            time.sleep(10)
            backups = self.depl.get_backups()
        self.check_command("rm %s/back-me-up" % (path))
        self.depl.restore(backup_id=backup_id)
        self.check_command(
            "echo -n important-data | diff %s/back-me-up -" % (path))

    def test_simple_restore(self):
        self.backup_and_restore_path()

    def test_raid_restore(self):
        self.depl.nix_exprs = self.depl.nix_exprs +\
            ['%s/single_machine_ec2_raid-0.nix' % (parent_dir)]
        self.backup_and_restore_path("/data")

    def check_command(self, command):
        self.depl.evaluate()
        machine = self.depl.machines.values()[0]
        return machine.run_command(command)
