from typing import Dict, Type
import nixops.plugins
from nixops.storage import StorageBackend
from nixops.storage.legacy import LegacyBackend
from nixops.storage.memory import MemoryBackend
from nixops.storage.s3 import S3Backend


@nixops.plugins.hookimpl
def register_backends() -> Dict[str, Type[StorageBackend]]:
    return {"legacy": LegacyBackend, "s3": S3Backend, "memory": MemoryBackend}
