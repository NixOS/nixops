from dataclasses import dataclass
import subprocess
import typing
import json


@dataclass
class GenericStorageConfig:
    provider: str
    configuration: typing.Dict[typing.Any, typing.Any]


@dataclass
class NetworkEval:
    storage: GenericStorageConfig
    description: str = "Unnamed NixOps network"
    enableRollback: bool = False


def _eval_attr(
    attr, nix_exprs: typing.List[str]
) -> typing.Dict[typing.Any, typing.Any]:
    p = subprocess.run(
        [
            "nix-instantiate",
            "--eval-only",
            "--json",
            "--strict",
            # Arg
            "--arg",
            "checkConfigurationOptions",
            "false",
            # Attr
            "-A",
            attr,
        ]
        + nix_exprs,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode())

    return json.loads(p.stdout)


def eval_network(nix_exprs: typing.List[str]) -> NetworkEval:
    result = _eval_attr("network", nix_exprs)

    storage = result.get("storage")
    if storage is None:
        raise Exception("Missing property: network.storage must be configured.")
    if len(storage.keys()) > 1:
        raise Exception(
            "Invalid property: network.storage can only have one defined storage backend."
        )

    key = list(storage.keys()).pop()
    if key is None:
        raise Exception(
            "Missing property: network.storage has no defined storage backend."
        )

    result["storage"] = GenericStorageConfig(provider=key, configuration=storage[key])

    return NetworkEval(**result)
