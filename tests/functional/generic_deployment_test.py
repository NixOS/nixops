import os
import subprocess
import sqlite3
from charon import deployment

from tests.functional import db

class GenericDeploymentTest(object):
    _multiprocess_can_split_ = True

    def setup(self):
        self.depl = deployment.create_deployment(db())
        self.depl.auto_response = "y"

    def teardown(self):
        self.depl.destroy_vms()

    def check_command(self, command, machine=None, user="root"):
        if machine == None:
            self.depl.evaluate()
            machine = self.depl.machines.values()[0]

        ssh_name = machine.get_ssh_name()
        return (subprocess.call(["ssh", user + "@" + ssh_name] + machine.get_ssh_flags() + [ command ]) == 0)

    def set_ec2_args(self):
        assert os.getenv("EC2_SECURITY_GROUP") is not None, "The EC2_SECURITY_GROUP env var must be set to the name of an ec2 security group with inbound ssh access"
        assert os.getenv("EC2_KEY_PAIR") is not None, "The EC2_KEY_PAIR env var must be set to the name of an ec2 keypair"
        assert os.getenv("EC2_PRIVATE_KEY_FILE") is not None, "The EC2_PRIVATE_KEY_FILE env var must be set to the private key of an ec2 keypair"

        self.depl.set_argstr("securityGroup", os.getenv("EC2_SECURITY_GROUP"))
        self.depl.set_argstr("keyPair", os.getenv("EC2_KEY_PAIR"))
        self.depl.set_argstr("privateKey", os.getenv("EC2_PRIVATE_KEY_FILE"))
