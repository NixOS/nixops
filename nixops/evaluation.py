from dataclasses import dataclass
import subprocess
import typing
import json


@dataclass
class NetworkEval:

    description: str = "Unnamed NixOps network"
    enableRollback: bool = False
    enableState: bool = True


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
    return NetworkEval(**result)
