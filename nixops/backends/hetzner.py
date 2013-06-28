# -*- coding: utf-8 -*-
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
                                   ("robot_pass", "robotPass", "string")]:
            value = x.find("attr[@name='" + name + "']/" + valtype).get("value")
            setattr(self, var, value)


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

    public_ipv4 = nixops.util.attr_property("publicIpv4", None)

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
        if self._robot is not None: return
        self._robot = Robot(self.robot_user, self.robot_pass)

    def _wait_for_rescue(self, ip):
        self.log_start("waiting for rescue system...")
        nixops.util.wait_for_tcp_port(ip, 22, open=False,
                                      callback=lambda: self.log_continue("."))
        self.log_continue("[down]")
        nixops.util.wait_for_tcp_port(ip, 22,
                                      callback=lambda: self.log_continue("."))
        self.log_end("[up]")
        self.state = self.RESCUE

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, HetznerDefinition)
        self.set_common_state(defn)

        if not self.vm_id:
            self.robot_user = defn.robot_user
            self.robot_pass = defn.robot_pass
            server = self._get_server_by_ip(defn.main_ipv4)

            if not server.rescue.active:
                self.log("rebooting machine ‘{0}’ ({1}) into rescue"
                         .format(self.name, defn.main_ipv4))
                server.rescue.activate()
                server.reboot('hard')
                self._wait_for_rescue(defn.main_ipv4)

            connection = server.rescue.connect()
            connection.close()

    def start(self):
        server = self._get_server_by_ip(defn.main_ipv4)
        server.reboot()

    def stop(self):
        """
        "Stops" the server by putting it into the rescue system.
        """
        pass

    def get_ssh_name(self):
        assert self.public_ipv4
        return self.public_ipv4

    def _get_server_by_ip(self, ip):
        """
        Return the server robot instance by its main IPv4 address.
        """
        self.connect()
        return self._robot.servers.get(ip)

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        self.connect()
        server = self._get_server_by_ip(self.main_ipv4)
        # TODO...

    def destroy(self):
        return True
