import subprocess
import typing
from typing import Optional, Mapping, Any
import json
from nixops.util import ImmutableValidatedObject


class GenericStorageConfig(ImmutableValidatedObject):
    provider: str
    configuration: typing.Mapping[typing.Any, typing.Any]


class NetworkEval(ImmutableValidatedObject):
    storage: GenericStorageConfig
    description: str = "Unnamed NixOps network"
    enableRollback: bool = False


class RawNetworkEval(ImmutableValidatedObject):
    storage: Mapping[str, Any]
    description: Optional[str]
    enableRollback: Optional[bool]


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
    raw_eval = RawNetworkEval(**_eval_attr("network", nix_exprs))

    if len(raw_eval.storage) > 1:
        raise Exception(
            "Invalid property: network.storage can only have one defined storage backend."
        )

    try:
        key = list(raw_eval.storage.keys()).pop()
        value = raw_eval.storage[key]
    except KeyError:
        raise Exception(
            "Missing property: network.storage has no defined storage backend."
        )

    return NetworkEval(
        enableRollback=raw_eval.enableRollback or False,
        description=raw_eval.description or "Unnamed NixOps network",
        storage={"provider": key, "configuration": value},
    )
