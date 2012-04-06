# -*- coding: utf-8 -*-

from charon.backends import MachineDefinition, MachineState

class NoneDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"
    
    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        self._target_host = xml.find("attrs/attr[@name='targetHost']/string").get("value")

    def make_state():
        return MachineState()


class NoneState(MachineState):
    """State of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"
    
    def __init__(self, depl, name):
        MachineState.__init__(self, depl, name)
        
    def create(self, defn, check):
        assert isinstance(defn, NoneDefinition)
        self._target_host = defn._target_host

    def serialise(self):
        x = MachineState.serialise(self)
        x['targetHost'] = self._target_host
        return x

    def deserialise(self, x):
        MachineState.deserialise(self, x)
        self._target_host = x['targetHost']
        
    def get_ssh_name(self):
        return self._target_host
