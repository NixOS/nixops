from nixops.transports.local import LocalTransport
from nixops.backends.none import NoneDefinition, NoneState
from nixops.backends import Transport
from typing import Type


class LocalDefinition(NoneDefinition):
    @classmethod
    def get_type(cls):
        return "local"


class LocalState(NoneState):

    transport_type: Type[Transport] = LocalTransport

    @classmethod
    def get_type(cls):
        return "local"
