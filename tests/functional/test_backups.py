import time

from os import path

from nose import tools
from nose.plugins.attrib import attr
from tests.functional import generic_deployment_test

from nixops.evaluation import NetworkFile

parent_dir = path.dirname(__file__)


@attr("ec2")
class TestBackups(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestBackups, self).setup()

    def test_simple_restore_xd_device_mapping(self):
        return
        self.depl.nix_exprs = [
            "%s/single_machine_logical_base.nix" % (parent_dir),
            "%s/single_machine_ec2_ebs.nix" % (parent_dir),
            "%s/single_machine_ec2_base.nix" % (parent_dir),
        ]
        self.backup_and_restore_path()

    def test_simple_restore_on_nvme_device_mapping(self):
        return
        self.depl.nix_exprs = [
            "%s/single_machine_logical_base.nix" % (parent_dir),
            "%s/single_machine_ec2_ebs.nix" % (parent_dir),
            "%s/single_machine_ec2_base_nvme.nix" % (parent_dir),
        ]
        self.backup_and_restore_path()

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
        machine = next(iter(self.depl.machines.values()))
        return machine.run_command(command)
