from typing import Dict, Type
import nixops.plugins
from nixops.storage import StorageBackend
from nixops.storage.legacy import LegacyBackend
from nixops.storage.memory import MemoryBackend


@nixops.plugins.hookimpl
def register_backends() -> Dict[str, Type[StorageBackend]]:
    return {"legacy": LegacyBackend, "memory": MemoryBackend}
