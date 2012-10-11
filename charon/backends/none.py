# -*- coding: utf-8 -*-

from charon.backends import MachineDefinition, MachineState
import charon.util
import sys

class NoneDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        self._target_host = xml.find("attrs/attr[@name='targetHost']/string").get("value")


class NoneState(MachineState):
    """State of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"

    target_host = charon.util.attr_property("targetHost", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)

    def create(self, defn, check, allow_reboot):
        assert isinstance(defn, NoneDefinition)
        self.target_host = defn._target_host

    def get_ssh_name(self):
        return self.target_host

    def destroy(self):
        # No-op; just forget about the machine.
        return True
