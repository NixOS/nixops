# -*- coding: utf-8 -*-

import sys


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

        # Nix store path of the last global configuration deployed to
        # this machine.  Used to check whether this machine is up to
        # date with respect to the global configuration.
        self.cur_configs_path = None

        # Nix store path of the last machine configuration deployed to
        # this machine.
        self.cur_toplevel = None
        
    def create(self, defn):
        """Create or update the machine instance defined by ‘defn’, if appropriate."""
        assert False

    def serialise(self):
        """Return a dictionary suitable for representing the on-disk state of this machine."""
        x = { }
        if self.cur_configs_path: x['vmsPath'] = self.cur_configs_path
        if self.cur_toplevel: x['toplevel'] = self.cur_toplevel
        return x

    def deserialise(self, x):
        """Deserialise the state from the given dictionary."""
        self.cur_configs_path = x.get('vmsPath', None)
        self.cur_toplevel = x.get('toplevel', None)

    def destroy(self):
        """Destroy this machine, if possible."""
        print >> sys.stderr, "warning: don't know how to destroy machine ‘{0}’".format(self.name)

    def get_ssh_name(self):
        assert False

    def get_physical_spec(self):
        return []

    @property
    def vm_id(self):
        return None

    @property
    def public_ipv4(self):
        return None
    
    @property
    def private_ipv4(self):
        return None
    

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
    raise Exception("unknown backend type ‘{0}’".format(type))
