from nixops.storage import StorageArgValues
import nixops.statefile
import sys
import os
import os.path


class LegacyBackend:
    def __init__(self, args: StorageArgValues) -> None:
        pass

    # fetchToFile: acquire a lock and download the state file to
    # the local disk. Note: no arguments will be passed over kwargs.
    # Making it part of the type definition allows adding new
    # arguments later.
    def fetchToFile(self, path: str, **kwargs) -> None:
        os.symlink(os.path.abspath(self.state_location()), path)

    def onOpen(self, sf: nixops.statefile.StateFile, **kwargs) -> None:
        pass

    def state_location(self) -> str:
        env_override = os.environ.get("NIXOPS_STATE", os.environ.get("CHARON_STATE"))
        if env_override is not None:
            return env_override

        home_dir = os.environ.get("HOME", "")
        charon_dir = f"{home_dir}/.charon"
        nixops_dir = f"{home_dir}/.nixops"

        if not os.path.exists(nixops_dir):
            if os.path.exists(charon_dir):
                sys.stderr.write(
                    "renaming ‘{0}’ to ‘{1}’...\n".format(charon_dir, nixops_dir)
                )
                os.rename(charon_dir, nixops_dir)
                if os.path.exists(nixops_dir + "/deployments.charon"):
                    os.rename(
                        nixops_dir + "/deployments.charon",
                        nixops_dir + "/deployments.nixops",
                    )
            else:
                os.makedirs(nixops_dir, 0o700)

        return nixops_dir + "/deployments.nixops"

    # uploadFromFile: upload the new state file and release any locks
    # Note: no arguments will be passed over kwargs. Making it part of
    # the type definition allows adding new arguments later.
    def uploadFromFile(self, path: str, **kwargs) -> None:
        pass
