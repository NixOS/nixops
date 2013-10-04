import socket
from os import path

from nose import tools

from tests.functional import generic_deployment_test

parent_dir = path.dirname(__file__)

logical_spec = '%s/single_machine_logical_base.nix' % (parent_dir)

class TestSecurityGroups(generic_deployment_test.GenericDeploymentTest):
    _multiprocess_can_split_ = True

    def setup(self):
        super(TestSecurityGroups,self).setup()
        self.set_ec2_args()
        self.depl.set_arg("openPort", "false")
        self.depl.set_arg("enableSecurityGroup", "false")
        self.depl.nix_exprs = [ logical_spec,
                '%s/single_machine_ec2_security_groups.nix' % (parent_dir),
                '%s/single_machine_ec2_base.nix' % (parent_dir)
                ]

    def test_open_ports(self):
        self.depl.deploy()
        machine = self.depl.machines.values()[0]
        machine.run_command("ncat -kl -p 3030 &")
        tools.assert_raises(socket.timeout, socket.create_connection, ((machine.public_ipv4, 3030), 5))

        self.depl.set_arg("openPort", "true")
        self.depl.set_arg("enableSecurityGroup", "true")
        self.depl.deploy()
        socket.create_connection((machine.public_ipv4, 3030), 5).close()

        self.depl.set_arg("openPort", "false")
        self.depl.deploy()
        tools.assert_raises(socket.timeout, socket.create_connection, ((machine.public_ipv4, 3030), 5))

        self.depl.set_arg("openPort", "true")
        self.depl.deploy()
        socket.create_connection((machine.public_ipv4, 3030), 5).close()
