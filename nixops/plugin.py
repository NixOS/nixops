from nixops.storage import BackendRegistration
from nixops.storage.legacy import LegacyBackend
from nixops.storage.memory import MemoryBackend
import nixops.plugins


class InternalPlugin(nixops.plugins.Plugin):
    def storage_backends(self) -> BackendRegistration:
        return {"legacy": LegacyBackend, "memory": MemoryBackend}


@nixops.plugins.hookimpl
def plugin():
    return InternalPlugin()
