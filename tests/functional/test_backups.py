import time

from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/single_machine_logical_base.nix' % (parent_dir)

class TestBackups(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestBackups,self).setup()
        self.set_ec2_args()
        self.depl.nix_exprs = [ logical_spec,
                '%s/single_machine_ec2_ebs.nix' % (parent_dir),
                '%s/single_machine_ec2_base.nix' % (parent_dir)
                ]

    def test_simple_restore(self):
        pass
#       self.depl.deploy()
#       tools.assert_true(self.check_command("echo -n important-data > /back-me-up"))
#       backup_id = self.depl.backup()
#       backups = self.depl.get_backups()
#       while backups[backup_id]['status'] == "running":
#           time.sleep(10)
#           backups = self.depl.get_backups()
#       tools.assert_true(self.check_command("rm /back-me-up"))
#       self.depl.restore(backup_id=backup_id)
#       tools.assert_true(self.check_command("echo -n important-data | diff /back-me-up -"))

    def check_command(self, command, user="root"):
        self.depl.evaluate()
        machine = self.depl.machines.values()[0]
        return super(TestBackups,self).check_command(command, machine, user)
