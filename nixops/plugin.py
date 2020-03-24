from nixops.storage import StorageBackend, BackendRegistration
from nixops.storage.legacy import LegacyBackend
import nixops.plugins


class InternalPlugin(nixops.plugins.Plugin):

    def storage_backends(self) -> BackendRegistration:
        return {"legacy": LegacyBackend}


@nixops.plugins.hookimpl
def plugin():
    return InternalPlugin()
