import time

from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

class TestEc2WithNvmeDeviceMapping(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestEc2WithNvmeDeviceMapping,self).setup()

    def test_ec2_with_nvme_device_mapping(self):
        self.depl.nix_exprs = [
            '%s/ec2_with_nvme_device_mapping.nix' % (parent_dir),
        ]
        self.depl.deploy()
        self.check_command("test -f /etc/NIXOS")
        self.check_command("lsblk | grep nvme1n1")
        self.check_command("cat /proc/mounts | grep '/dev/nvme1n1 /data ext4 rw,relatime,data=ordered 0 0'")
        self.check_command("touch /data/asdf")

    def check_command(self, command):
        self.depl.evaluate()
        machine = self.depl.machines.values()[0]
        return machine.run_command(command)
