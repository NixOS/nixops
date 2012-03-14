from charon.backends import MachineDefinition, MachineState

class NoneDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"
    
    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        self.target_host = xml.find("attrs/attr[@name='targetHost']/string").get("value")

    def make_state():
        return MachineState()


class NoneState(MachineState):
    """State of a trivial machine."""

    @classmethod
    def get_type(cls):
        return "none"
    
    def __init__(self, name):
        MachineState.__init__(self, name)
        
    def create(self, defn):
        assert isinstance(defn, NoneDefinition)
        self.target_host = defn.target_host

    def serialise(self):
        return {'targetHost': self.target_host}

    def deserialise(self, x):
        self.target_host = x['targetHost']
