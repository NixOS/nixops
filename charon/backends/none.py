from charon.backends import MachineDefinition, MachineState

class NoneDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"
    
    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)

    def make_state():
        return MachineState()


class NoneState(MachineState):
    """State of a trivial machine."""

    def create():
        pass

    def get_info_from_xml():
        pass

    def serialise():
        return {}


