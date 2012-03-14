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

    def create():
        pass

    def get_info_from_xml():
        pass

    def serialise():
        return {}


import charon.backends.none

def create_definition(xml):
    target_env = xml.find("attrs/attr[@name='targetEnv']/string").get("value")
    for i in [charon.backends.none.NoneDefinition]:
        if target_env == i.get_type():
            return charon.backends.none.NoneDefinition(xml)
    raise Exception("unknown backend type ‘{0}’".format(target_env))
