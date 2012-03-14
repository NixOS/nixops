# -*- coding: utf-8 -*-


class MachineDefinition:
    """Base class for Charon backend machine definitions."""
    
    @classmethod
    def get_type(cls):
        assert False

    def __init__(self, xml):
        self.name = xml.get("name")
        assert self.name


class MachineState:
    """Base class for Charon backends machine states."""

    @classmethod
    def get_type(cls):
        assert False

    def __init__(self, name):
        self.name = name
        
    def create(self, defn):
        """Create or update the machine instance defined by ‘defn’, if appropriate."""
        assert False

    def serialise(self):
        """Return a dictionary suitable for representing the on-disk state of this machine."""
        assert False

    def deserialise(self, x):
        """Deserialise the state from the given dictionary."""
        assert False


import charon.backends.none

def create_definition(xml):
    """Create a machine definition object from the given XML representation of the machine's attributes."""
    target_env = xml.find("attrs/attr[@name='targetEnv']/string").get("value")
    for i in [charon.backends.none.NoneDefinition]:
        if target_env == i.get_type():
            return i(xml)
    raise Exception("unknown backend type ‘{0}’".format(target_env))

def create_state(type, name):
    """Create a machine state object of the desired backend type."""
    for i in [charon.backends.none.NoneState]:
        if type == i.get_type():
            return i(name)
    raise Exception("unknown backend type ‘{0}’".format(target_env))
