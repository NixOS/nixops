# -*- coding: utf-8 -*-
import os
import sys
import subprocess

import nixops.util
from nixops.hetzner_utils import Robot
from nixops.backends import MachineDefinition, MachineState


class HetznerDefinition(MachineDefinition):
    """
    Definition of a Hetzner machine.
    """

    @classmethod
    def get_type(cls):
        return "hetzner"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='hetzner']/attrs")
        assert x is not None
        for var, name, valtype in [("main_ipv4", "mainIPv4", "string"),
                                   ("robot_user", "robotUser", "string"),
                                   ("robot_pass", "robotPass", "string"),
                                   ("partitions", "partitions", "string")]:
            attr = x.find("attr[@name='" + name + "']/" + valtype)
            setattr(self, var, attr.get("value"))


class HetznerState(MachineState):
    """
    State of a Hetzner machine.
    """

    @classmethod
    def get_type(cls):
        return "hetzner"

    state = nixops.util.attr_property("state", MachineState.UNKNOWN, int)

    main_ipv4 = nixops.util.attr_property("hetzner.mainIPv4", None)
    robot_user = nixops.util.attr_property("hetzner.robotUser", None)
    robot_pass = nixops.util.attr_property("hetzner.robotPass", None)
    partitions = nixops.util.attr_property("hetzner.partitions", None)

    rescue_passwd = nixops.util.attr_property("rescuePasswd", None)
    partitioner = nixops.util.attr_property("rescuePartitioner", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._robot = None

    @property
    def resource_id(self):
        return self.vm_id

    def connect(self):
        """
        Connect to the Hetzner robot.
        """
        if self._robot is not None:
            return True
        elif self.robot_user is None or self.robot_pass is None:
            return False
        self._robot = Robot(self.robot_user, self.robot_pass)
        return True

    def _wait_for_rescue(self, ip):
        self.log_start("waiting for rescue system...")
        nixops.util.wait_for_tcp_port(ip, 22, open=False,
                                      callback=lambda: self.log_continue("."))
        self.log_continue("[down]")
        nixops.util.wait_for_tcp_port(ip, 22,
                                      callback=lambda: self.log_continue("."))
        self.log_end("[up]")
        self.state = self.RESCUE

    def _boot_into_rescue(self):
        if self.state == self.RESCUE:
            return

        self.log("rebooting machine ‘{0}’ ({1}) into rescue"
                 .format(self.name, self.main_ipv4))
        server = self._get_server_by_ip(self.main_ipv4)
        server.rescue.activate()
        rescue_passwd = server.rescue.password
        server.reboot('hard')
        self._wait_for_rescue(self.main_ipv4)
        self.rescue_passwd = rescue_passwd
        self.has_partitioner = None
        self.state = self.RESCUE

    def _build_partitioner(self):
        return subprocess.check_output([
            "nix-build", "<nixpkgs>", "--no-out-link",
            "-A", "pythonPackages.nixpartHetzner"
        ]).rstrip()

    def _install_partitioner(self):
        self.log_start("building partitioner...")
        nixpart = self._build_partitioner()
        self.log_end("done ({0})".format(nixpart))

        if self.partitioner is not None and self.partitioner == nixpart:
            return nixpart

        self.log_start("copying partitioner to rescue...")
        paths = subprocess.check_output(['nix-store', '-qR', nixpart])
        local_tar = subprocess.Popen(['tar', 'cJ'] + paths.splitlines(),
                                     stdout=subprocess.PIPE)
        self.run_command("tar xJ -C /", stdin=local_tar.stdout)
        self.log_end("done.")

        self.partitioner = nixpart
        return nixpart

    def _install_base_system(self):
        if self.state != self.RESCUE:
            return

        nixpart = self._install_partitioner()

        self.log_start("partitioning disks...")
        nixpart_bin = os.path.join(nixpart, "bin/nixpart")
        out = self.run_command("{0} -".format(nixpart_bin),
                               capture_stdout=True,
                               stdin_string=self.partitions)
        self.log_end("done.")
        self.log("partitioner output: {0}".format(out))

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, HetznerDefinition)

        if self.state not in (self.RESCUE, self.UP) or check:
            self.check()

        self.set_common_state(defn)
        self.robot_user = defn.robot_user
        self.robot_pass = defn.robot_pass
        self.main_ipv4 = defn.main_ipv4
        self.partitions = defn.partitions

        if not self.vm_id:
            self.log("installing machine...")
            vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)
            self._boot_into_rescue()
            self._install_base_system()

    def start(self):
        server = self._get_server_by_ip(defn.main_ipv4)
        server.reboot()

    def stop(self):
        """
        "Stops" the server by putting it into the rescue system.
        """
        pass

    def get_ssh_name(self):
        assert self.main_ipv4
        return self.main_ipv4

    def get_ssh_password(self):
        if self.state == self.RESCUE:
            return self.rescue_passwd
        else:
            return None

    def _get_server_by_ip(self, ip):
        """
        Return the server robot instance by its main IPv4 address.
        """
        if self.connect():
            return self._robot.servers.get(ip)
        else:
            return None

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        server = self._get_server_by_ip(self.main_ipv4)
        if server.rescue.active and self.rescue_passwd is not None:
            res.is_up = True
            self.state = self.RESCUE
        else:
            res.is_up = nixops.util.ping_tcp_port(self.main_ipv4, 22)
            MachineState._check(self, res)

    def destroy(self):
        return True
