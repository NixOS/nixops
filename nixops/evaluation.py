import subprocess
import typing
from typing import Optional, Mapping, Any
import json
from nixops.util import ImmutableValidatedObject
from nixops.exceptions import NixError


class MalformedNetworkError(NixError):
    pass


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


class EvalResult(ImmutableValidatedObject):
    exists: bool
    value: Any


def _eval_attr(attr, nix_expr: str) -> EvalResult:
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
            "--argstr",
            "attr",
            attr,
            "--arg",
            "nix_expr",
            nix_expr,
            "--expr",
            """
              { nix_expr, attr }:
              let
                ret = (import nix_expr);
              in {
                exists = ret ? "${attr}";
                value = ret."${attr}" or null;
              }
            """,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode())

    return EvalResult(**json.loads(p.stdout))


def eval_network(nix_expr: str) -> NetworkEval:
    result = _eval_attr("network", nix_expr)
    if not result.exists:
        raise MalformedNetworkError(
            """
TODO: improve this error to be less specific about conversion. link to
docs?


WARNING: NixOps 1.0 -> 2.0 conversion step required

NixOps 2.0 added support for multiple storage backends.

Upgrade steps:
1. Open %s
2. Add:
    network.storage.legacy = {
      databasefile = "~/.nixops/deployments.nixops"
    }
3. Rerun
"""
            % nix_expr
        )

    raw_eval = RawNetworkEval(**result.value)

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
