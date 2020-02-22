import time

from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)


class TestBackups(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestBackups, self).setup()

    def test_simple_restore_xd_device_mapping(self):
        self.depl.nix_exprs = [
            "%s/single_machine_logical_base.nix" % (parent_dir),
            "%s/single_machine_ec2_ebs.nix" % (parent_dir),
            "%s/single_machine_ec2_base.nix" % (parent_dir),
        ]
        self.backup_and_restore_path()

    def test_raid_restore_xd_device_mapping(self):
        self.depl.nix_exprs = [
            "%s/single_machine_logical_base.nix" % (parent_dir),
            "%s/single_machine_ec2_ebs.nix" % (parent_dir),
            "%s/single_machine_ec2_base.nix" % (parent_dir),
            "%s/single_machine_ec2_raid-0.nix" % (parent_dir),
        ]
        self.backup_and_restore_path("/data")

    def test_simple_restore_on_nvme_device_mapping(self):
        self.depl.nix_exprs = [
            "%s/single_machine_logical_base.nix" % (parent_dir),
            "%s/single_machine_ec2_ebs.nix" % (parent_dir),
            "%s/single_machine_ec2_base_nvme.nix" % (parent_dir),
        ]
        self.backup_and_restore_path()

    def test_raid_restore_on_nvme_device_mapping(self):
        self.depl.nix_exprs = [
            "%s/single_machine_logical_base.nix" % (parent_dir),
            "%s/single_machine_ec2_ebs.nix" % (parent_dir),
            "%s/single_machine_ec2_base_nvme.nix" % (parent_dir),
            "%s/single_machine_ec2_raid-0-nvme.nix" % (parent_dir),
        ]
        self.backup_and_restore_path("/data")
        self.check_command("mount | grep '/dev/mapper/raid-raid on /data type ext4'")
        self.check_command("mount | grep '/dev/nvme0n1p1 on /'")

    def backup_and_restore_path(self, path=""):
        self.depl.deploy()
        self.check_command("echo -n important-data > %s/back-me-up" % (path))
        backup_id = self.depl.backup()
        backups = self.depl.get_backups()
        while backups[backup_id]["status"] == "running":
            time.sleep(10)
            backups = self.depl.get_backups()
        self.check_command("rm %s/back-me-up" % (path))
        self.depl.restore(backup_id=backup_id)
        self.check_command("echo -n important-data | diff %s/back-me-up -" % (path))

    def check_command(self, command):
        self.depl.evaluate()
        machine = self.depl.machines.values()[0]
        return machine.run_command(command)
