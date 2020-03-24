from typing import Dict, Type
import nixops.plugins
from nixops.storage import StorageBackend
from nixops.storage.legacy import LegacyBackend


@nixops.plugins.hookimpl
def register_backends() -> Dict[str, Type[StorageBackend]]:
    return {"legacy": LegacyBackend}
