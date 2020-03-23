from typing import Dict, Type
import nixops.plugins
from nixops.storage import StorageBackend


@nixops.plugins.hookimpl
def register_backends() -> Dict[str, Type[StorageBackend]]:
    return {}
