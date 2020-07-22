# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import os.path
import subprocess
import json
import tempfile
import threading
from collections import defaultdict
import re
from datetime import datetime, timedelta
import nixops.statefile
import getpass
import traceback
import glob
import fcntl
import itertools
import platform
import time
import importlib

from functools import reduce
from typing import (
    Callable,
    Dict,
    Optional,
    TextIO,
    Set,
    List,
    DefaultDict,
    Any,
    Tuple,
    Union,
    cast,
    TypeVar,
    Type,
)
import nixops.backends
import nixops.logger
import nixops.parallel
from nixops.plugins.manager import (
    DeploymentHooksManager,
    MachineHooksManager,
    PluginManager,
)

from nixops.nix_expr import RawValue, Function, Call, nixmerge, py2nix
from nixops.ansi import ansi_success


Definitions = Dict[str, nixops.resources.ResourceDefinition]


class NixEvalError(Exception):
    pass


class UnknownBackend(Exception):
    pass


DEBUG = False

NixosConfigurationType = List[Dict[Tuple[str, ...], Any]]

TypedResource = TypeVar("TypedResource")
TypedDefinition = TypeVar("TypedDefinition")


class Deployment:
    """NixOps top-level deployment manager."""

    default_description = "Unnamed NixOps network"

    name: Optional[str] = nixops.util.attr_property("name", None)
    nix_exprs = nixops.util.attr_property("nixExprs", [], "json")
    nix_path = nixops.util.attr_property("nixPath", [], "json")
    flake_uri = nixops.util.attr_property("flakeUri", None)
    cur_flake_uri = nixops.util.attr_property("curFlakeUri", None)
    args = nixops.util.attr_property("args", {}, "json")
    description = nixops.util.attr_property("description", default_description)
    configs_path = nixops.util.attr_property("configsPath", None)
    rollback_enabled: bool = nixops.util.attr_property("rollbackEnabled", False)

    # internal variable to mark if network attribute of network has been evaluated (separately)
    network_attr_eval: bool = False

    def __init__(
        self, statefile, uuid: str, log_file: TextIO = sys.stderr,
    ):
        self._statefile = statefile
        self._db: nixops.statefile.Connection = statefile._db
        self.uuid = uuid

        self._last_log_prefix = None
        self.extra_nix_path: List[str] = []
        self.extra_nix_flags: List[str] = []
        self.extra_nix_eval_flags: List[str] = []
        self.nixos_version_suffix: Optional[str] = None
        self._tempdir: Optional[nixops.util.SelfDeletingDir] = None

        self.logger = nixops.logger.Logger(log_file)

        self._lock_file_path: Optional[str] = None

        self.expr_path = os.path.realpath(
            os.path.dirname(__file__) + "/../../../../share/nix/nixops"
        )
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.realpath(
                os.path.dirname(__file__) + "/../../../../../share/nix/nixops"
            )
        if not os.path.exists(self.expr_path):
            self.expr_path = os.path.dirname(__file__) + "/../nix"

        self.resources: Dict[str, nixops.resources.GenericResourceState] = {}
        with self._db:
            c = self._db.cursor()
            c.execute(
                "select id, name, type from Resources where deployment = ?",
                (self.uuid,),
            )
            for (id, name, type) in c.fetchall():
                r = _create_state(self, type, name, id)
                self.resources[name] = r
        self.logger.update_log_prefixes()

        self.definitions: Optional[Definitions] = None

        self._cur_flake_uri: Optional[str] = None

    @property
    def tempdir(self) -> nixops.util.SelfDeletingDir:
        if not self._tempdir:
            self._tempdir = nixops.util.SelfDeletingDir(
                tempfile.mkdtemp(prefix="nixops-tmp")
            )
        return self._tempdir

    def _get_cur_flake_uri(self):
        assert self.flake_uri is not None
        if self._cur_flake_uri is None:
            out = json.loads(
                subprocess.check_output(
                    ["nix", "flake", "info", "--json", "--", self.flake_uri],
                    stderr=self.logger.log_file,
                )
            )
            self._cur_flake_uri = out["url"].replace(
                "ref=HEAD&rev=0000000000000000000000000000000000000000&", ""
            )  # FIXME
        return self._cur_flake_uri

    @property
    def machines(self) -> Dict[str, nixops.backends.GenericMachineState]:
        return _filter_machines(self.resources)

    @property
    def active(self) -> None:
        """
        Legacy alias for active_machines.
        Return type is set to None to make mypy fail and let plugin authors
        notice that they should not use this legacy name.
        """
        return self.active_machines  # type: ignore

    @property
    def active_machines(
        self,
    ) -> Dict[
        str, nixops.backends.GenericMachineState
    ]:  # FIXME: rename to "active_machines"
        return _filter_machines(self.active_resources)

    @property
    def active_resources(self) -> Dict[str, nixops.resources.GenericResourceState]:
        return {n: r for n, r in self.resources.items() if not r.obsolete}

    def get_generic_resource(
        self, name: str, type_name: str
    ) -> nixops.resources.GenericResourceState:
        res = self.active_resources.get(name, None)
        if not res:
            raise Exception("resource ‘{0}’ does not exist".format(name))
        if res.get_type() != type_name:
            raise Exception(
                "resource ‘{0}’ is not of type ‘{1}’".format(name, type_name)
            )
        return res

    def get_typed_resource(
        self, name: str, type_name: str, type: Type[TypedResource]
    ) -> TypedResource:
        res = self.get_generic_resource(name, type_name)
        if not isinstance(res, type):
            raise ValueError(f"{res} not of type {type}")
        return res

    def get_generic_definition(
        self, name: str, type_name: str
    ) -> nixops.resources.ResourceDefinition:
        defn = self._definitions().get(name, None)
        if not defn:
            raise Exception("definition ‘{0}’ does not exist".format(name))
        if defn.get_type() != type_name:
            raise Exception(
                "definition ‘{0}’ is not of type ‘{1}’".format(name, type_name)
            )
        return defn

    def get_typed_definition(
        self, name: str, type_name: str, type: Type[TypedDefinition]
    ) -> TypedDefinition:
        defn = self.get_generic_definition(name, type_name)
        if not isinstance(defn, type):
            raise ValueError(f"{defn} not of type {type}")
        return defn

    def get_machine(self, name: str, type: Type[TypedResource]) -> TypedResource:
        m = self.get_generic_machine(name)
        if not isinstance(m, type):
            raise ValueError(f"{m} not of type {type}")
        return m

    def get_generic_machine(self, name: str) -> nixops.resources.GenericResourceState:
        res = self.active_resources.get(name, None)
        if not res:
            raise Exception("machine ‘{0}’ does not exist".format(name))
        if not is_machine(res):
            raise Exception("resource ‘{0}’ is not a machine".format(name))
        return res

    def _definitions(self) -> Definitions:
        if self.definitions is None:
            raise Exception("Bug: Deployment.definitions is None.")
        return self.definitions

    def _definition_for(
        self, name: str
    ) -> Optional[nixops.resources.ResourceDefinition]:
        definitions = self._definitions()

        return definitions[name]

    def _definition_for_required(
        self, name: str
    ) -> nixops.resources.ResourceDefinition:
        defn = self._definition_for(name)
        if defn is None:
            raise Exception("Bug: Deployment.definitions['{}'] is None.".format(name))
        return defn

    def _machine_definition_for_required(
        self, name: str
    ) -> nixops.backends.MachineDefinition:
        defn = self._definition_for_required(name)
        if not isinstance(defn, nixops.backends.MachineDefinition):
            raise Exception("Definition named '{}' is not a machine.".format(name))
        return defn

    def _set_attrs(self, attrs: Dict[str, Optional[str]]) -> None:
        """Update deployment attributes in the state file."""
        with self._db:
            c = self._db.cursor()
            for n, v in attrs.items():
                if v is None:
                    c.execute(
                        "delete from DeploymentAttrs where deployment = ? and name = ?",
                        (self.uuid, n),
                    )
                else:
                    c.execute(
                        "insert or replace into DeploymentAttrs(deployment, name, value) values (?, ?, ?)",
                        (self.uuid, n, v),
                    )

    def _set_attr(self, name: str, value: Any) -> None:
        """Update one deployment attribute in the state file."""
        self._set_attrs({name: value})

    def _del_attr(self, name: str) -> None:
        """Delete a deployment attribute from the state file."""
        with self._db:
            self._db.execute(
                "delete from DeploymentAttrs where deployment = ? and name = ?",
                (self.uuid, name),
            )

    def _get_attr(self, name: str, default: Any = nixops.util.undefined) -> Any:
        """Get a deployment attribute from the state file."""
        with self._db:
            c = self._db.cursor()
            c.execute(
                "select value from DeploymentAttrs where deployment = ? and name = ?",
                (self.uuid, name),
            )
            row: List[Optional[Any]] = c.fetchone()
            if row is not None:
                return row[0]
            return nixops.util.undefined

    def _create_resource(
        self, name: str, type: str
    ) -> nixops.resources.GenericResourceState:
        c = self._db.cursor()
        c.execute(
            "select 1 from Resources where deployment = ? and name = ?",
            (self.uuid, name),
        )
        if len(c.fetchall()) != 0:
            raise Exception("resource already exists in database!")
        c.execute(
            "insert into Resources(deployment, name, type) values (?, ?, ?)",
            (self.uuid, name, type),
        )
        id = c.lastrowid
        r = _create_state(self, type, name, id)
        self.resources[name] = r
        return r

    def export(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        with self._db:
            c = self._db.cursor()
            c.execute(
                "select name, value from DeploymentAttrs where deployment = ?",
                (self.uuid,),
            )
            rows = c.fetchall()
            res = {row[0]: row[1] for row in rows}
            res["resources"] = {r.name: r.export() for r in self.resources.values()}
            return res

    def import_(self, attrs: Dict[str, Union[str, Dict[str, Dict[str, str]]]]) -> None:
        with self._db:
            for name, value in attrs.items():
                if name == "resources":
                    continue
                self._set_attr(name, value)

            if isinstance(attrs["resources"], dict):
                for k, v in attrs["resources"].items():
                    if "type" not in v:
                        raise Exception("imported resource lacks a type")
                    r = self._create_resource(k, v["type"])
                    r.import_(v)

    def clone(self) -> Deployment:
        with self._db:
            new = self._statefile.create_deployment()
            self._db.execute(
                "insert into DeploymentAttrs (deployment, name, value) "
                + "select ?, name, value from DeploymentAttrs where deployment = ?",
                (new.uuid, self.uuid),
            )
            new.configs_path = None
            return new

    def _get_deployment_lock(
        self,
    ) -> Any:  # FIXME: DeploymentLock is defined inside the function
        if self._lock_file_path is None:
            lock_dir = os.environ.get("HOME", "") + "/.nixops/locks"
            if not os.path.exists(lock_dir):
                os.makedirs(lock_dir, 0o700)
            self._lock_file_path = lock_dir + "/" + self.uuid

        class DeploymentLock(object):
            def __init__(self, depl: Deployment):
                assert depl._lock_file_path is not None
                self._lock_file_path: str = depl._lock_file_path
                self._logger: nixops.logger.Logger = depl.logger
                self._lock_file: Optional[TextIO] = None

            def __enter__(self) -> None:
                self._lock_file = open(self._lock_file_path, "w")
                fcntl.fcntl(self._lock_file, fcntl.F_SETFD, fcntl.FD_CLOEXEC)
                try:
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except IOError:
                    self._logger.log("waiting for exclusive deployment lock...")
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX)

            def __exit__(self, exception_type, exception_value, exception_traceback):
                if self._lock_file is not None:
                    self._lock_file.close()

        return DeploymentLock(self)

    def delete_resource(self, m: nixops.resources.GenericResourceState) -> None:
        del self.resources[m.name]
        with self._db:
            self._db.execute(
                "delete from Resources where deployment = ? and id = ?",
                (self.uuid, m.id),
            )

    def delete(self, force: bool = False) -> None:
        """Delete this deployment from the state file."""
        with self._db:
            if not force and len(self.resources) > 0:
                raise Exception(
                    "cannot delete this deployment because it still has resources"
                )

            # Delete the profile, if any.
            profile = self.get_profile()
            assert profile
            for p in glob.glob(profile + "*"):
                if os.path.islink(p):
                    os.remove(p)

            # Delete the deployment from the database.
            self._db.execute("delete from Deployments where uuid = ?", (self.uuid,))

    def _nix_path_flags(self) -> List[str]:
        extraexprs = PluginManager.nixexprs()

        flags = (
            list(
                itertools.chain(
                    *[
                        ["-I", x]
                        for x in (self.extra_nix_path + self.nix_path + extraexprs)
                    ]
                )
            )
            + self.extra_nix_flags
        )
        flags.extend(["-I", "nixops=" + self.expr_path])
        return flags

    def _eval_flags(self, exprs: List[str]) -> List[str]:
        flags = self._nix_path_flags()
        args = {key: RawValue(val) for key, val in self.args.items()}
        exprs_ = [RawValue(x) if x[0] == "<" else x for x in exprs]

        extraexprs = PluginManager.nixexprs()

        flags.extend(
            [
                "--arg",
                "networkExprs",
                py2nix(exprs_, inline=True),
                "--arg",
                "args",
                py2nix(args, inline=True),
                "--argstr",
                "uuid",
                self.uuid,
                "--argstr",
                "deploymentName",
                self.name if self.name else "",
                "--arg",
                "pluginNixExprs",
                py2nix(extraexprs),
                (self.expr_path + "/eval-machine-info.nix"),
            ]
        )

        if self.flake_uri is not None:
            flags.extend(
                [
                    # "--pure-eval", # FIXME
                    "--argstr",
                    "flakeUri",
                    self._get_cur_flake_uri(),
                    "--allowed-uris",
                    self.expr_path,
                ]
            )

        return flags

    def set_arg(self, name: str, value: str) -> None:
        """Set a persistent argument to the deployment specification."""
        assert isinstance(name, str)
        assert isinstance(value, str)
        args = self.args
        args[name] = value
        self.args = args

    def set_argstr(self, name: str, value: str) -> None:
        """Set a persistent argument to the deployment specification."""
        assert isinstance(value, str)
        self.set_arg(name, py2nix(value, inline=True))

    def unset_arg(self, name: str) -> None:
        """Unset a persistent argument to the deployment specification."""
        assert isinstance(name, str)
        args = self.args
        args.pop(name, None)
        self.args = args

    def evaluate_args(self) -> Any:
        """Evaluate the NixOps network expression's arguments."""
        try:
            out = subprocess.check_output(
                ["nix-instantiate"]
                + self.extra_nix_eval_flags
                + self._eval_flags(self.nix_exprs)
                + ["--eval-only", "--json", "--strict", "-A", "nixopsArguments"],
                stderr=self.logger.log_file,
                text=True,
            )
            if DEBUG:
                print("JSON output of nix-instantiate:\n" + out, file=sys.stderr)
            return json.loads(out)
        except OSError as e:
            raise Exception("unable to run ‘nix-instantiate’: {0}".format(e))
        except subprocess.CalledProcessError:
            raise NixEvalError

    def evaluate_config(self, attr) -> Dict:
        try:
            _json = subprocess.check_output(
                ["nix-instantiate"]
                + self.extra_nix_eval_flags
                + self._eval_flags(self.nix_exprs)
                + [
                    "--eval-only",
                    "--json",
                    "--strict",
                    "--arg",
                    "checkConfigurationOptions",
                    "false",
                    "-A",
                    attr,
                ],
                stderr=self.logger.log_file,
                text=True,
            )
            if DEBUG:
                print("JSON output of nix-instantiate:\n" + _json, file=sys.stderr)
        except OSError as e:
            raise Exception("unable to run ‘nix-instantiate’: {0}".format(e))
        except subprocess.CalledProcessError:
            raise NixEvalError

        return json.loads(_json)

    def evaluate_network(self, action: str = "") -> None:
        if not self.network_attr_eval:
            # Extract global deployment attributes.
            try:
                config = self.evaluate_config("info.network")
            except Exception as e:
                if action not in ("destroy", "delete"):
                    raise e
                config = {}
            self.description = config.get("description", self.default_description)
            self.rollback_enabled = config.get("enableRollback", False)
            self.network_attr_eval = True

    def evaluate(self) -> None:
        """Evaluate the Nix expressions belonging to this deployment into a deployment specification."""

        self.definitions = {}
        self.evaluate_network()

        config = self.evaluate_config("info")

        # Extract machine information.
        for name, cfg in config["machines"].items():
            defn = _create_definition(name, cfg, cfg["targetEnv"])
            self.definitions[name] = defn

        # Extract info about other kinds of resources.
        for res_type, cfg in config["resources"].items():
            for name, y in cfg.items():
                defn = _create_definition(
                    name, config["resources"][res_type][name], res_type
                )
                self.definitions[name] = defn

    def evaluate_option_value(
        self,
        machine_name: str,
        option_name: str,
        json: bool = False,
        xml: bool = False,
        include_physical: bool = False,
    ) -> str:
        """Evaluate a single option of a single machine in the deployment specification."""

        exprs = self.nix_exprs
        if include_physical:
            phys_expr = self.tempdir + "/physical.nix"
            with open(phys_expr, "w") as f:
                f.write(self.get_physical_spec())
            exprs.append(phys_expr)

        try:
            return subprocess.check_output(
                ["nix-instantiate"]
                + self.extra_nix_eval_flags
                + self._eval_flags(exprs)
                + [
                    "--eval-only",
                    "--strict",
                    "--arg",
                    "checkConfigurationOptions",
                    "false",
                    "-A",
                    "nodes.{0}.config.{1}".format(machine_name, option_name),
                ]
                + (["--json"] if json else [])
                + (["--xml"] if xml else []),
                stderr=self.logger.log_file,
                text=True,
            )
        except subprocess.CalledProcessError:
            raise NixEvalError

    def get_arguments(self) -> Any:
        try:
            return self.evaluate_args()
        except Exception:
            raise Exception("Could not determine arguments to NixOps deployment.")

    def get_physical_spec(self) -> Any:
        """Compute the contents of the Nix expression specifying the computed physical deployment attributes"""

        active_machines = self.active_machines
        active_resources = self.active_resources

        attrs_per_resource: Dict[str, NixosConfigurationType] = {
            m.name: [] for m in active_resources.values()
        }
        authorized_keys: Dict[str, List[str]] = {
            m.name: [] for m in active_machines.values()
        }
        kernel_modules: Dict[str, Set[str]] = {
            m.name: set() for m in active_machines.values()
        }
        trusted_interfaces: Dict[str, Set[str]] = {
            m.name: set() for m in active_machines.values()
        }

        for name, attrs in DeploymentHooksManager.physical_spec(self).items():
            attrs_per_resource[name].extend(attrs)

        # Hostnames should be accumulated like this:
        #
        #   hosts[local_name][remote_ip] = [name1, name2, ...]
        #
        # This makes hosts deterministic and is more in accordance to the
        # format in hosts(5), which is like this:
        #
        #   ip_address canonical_hostname [aliases...]
        #
        # This is critical for example when using host names for access
        # control, because the canonical_hostname is returned in reverse
        # lookups.
        hosts: DefaultDict[str, DefaultDict[str, List[str]]] = defaultdict(
            lambda: defaultdict(list)
        )

        def index_to_private_ip(index: int) -> str:
            n = 105 + index / 256
            assert n <= 255
            return "192.168.{0}.{1}".format(n, index % 256)

        def do_machine(m: nixops.backends.GenericMachineState) -> None:
            defn = self._machine_definition_for_required(m.name)

            attrs_list = attrs_per_resource[m.name]

            private_ipv4: Optional[str] = m.private_ipv4
            if private_ipv4:
                attrs_list.append({("networking", "privateIPv4"): private_ipv4})

            public_ipv4: Optional[str] = m.public_ipv4
            if public_ipv4:
                attrs_list.append({("networking", "publicIPv4"): public_ipv4})

            # Set system.stateVersion if the Nixpkgs version supports it.
            nixos_version = nixops.util.parse_nixos_version(defn.config.nixosRelease)
            if nixos_version >= ["15", "09"]:
                attrs_list.append(
                    {
                        ("system", "stateVersion"): Call(
                            RawValue("lib.mkDefault"),
                            m.state_version or defn.config.nixosRelease,
                        )
                    }
                )

            if self.nixos_version_suffix:
                if nixos_version >= ["18", "03"]:
                    attrs_list.append(
                        {
                            (
                                "system",
                                "nixos",
                                "versionSuffix",
                            ): self.nixos_version_suffix
                        }
                    )
                else:
                    attrs_list.append(
                        {("system", "nixosVersionSuffix"): self.nixos_version_suffix}
                    )

        for m in active_machines.values():
            do_machine(m)

        def emit_resource(r: nixops.resources.GenericResourceState) -> Any:
            config: NixosConfigurationType = []
            config.extend(attrs_per_resource[r.name])
            if is_machine(r):
                # Sort the hosts by its canonical host names.
                sorted_hosts = sorted(
                    hosts[r.name].items(), key=lambda item: item[1][0]
                )
                # Just to remember the format:
                #   ip_address canonical_hostname [aliases...]
                extra_hosts = [
                    "{0} {1}".format(ip, " ".join(names)) for ip, names in sorted_hosts
                ]

                if authorized_keys[r.name]:
                    config.append(
                        {
                            ("users", "extraUsers", "root"): {
                                ("openssh", "authorizedKeys", "keys"): authorized_keys[
                                    r.name
                                ]
                            },
                            ("services", "openssh"): {
                                "extraConfig": "PermitTunnel yes\n"
                            },
                        }
                    )

                config.append(
                    {
                        ("boot", "kernelModules"): list(kernel_modules[r.name]),
                        ("networking", "firewall"): {
                            "trustedInterfaces": list(trusted_interfaces[r.name])
                        },
                        ("networking", "extraHosts"): "\n".join(extra_hosts) + "\n",
                    }
                )

                # Add SSH public host keys for all machines in network.
                for m2 in active_machines.values():
                    if hasattr(m2, "public_host_key") and m2.public_host_key:
                        # Using references to files in same tempdir for now, until NixOS has support
                        # for adding the keys directly as string. This way at least it is compatible
                        # with older versions of NixOS as well.
                        # TODO: after reasonable amount of time replace with string option
                        config.append(
                            {
                                ("services", "openssh", "knownHosts", m2.name): {
                                    "hostNames": [m2.name],
                                    "publicKey": m2.public_host_key,
                                }
                            }
                        )

            merged = reduce(nixmerge, config) if len(config) > 0 else {}
            physical = r.get_physical_spec()

            if len(merged) == 0 and len(physical) == 0:
                return {}
            else:
                return r.prefix_definition(
                    {
                        r.name: Function(
                            "{ config, lib, pkgs, ... }",
                            {"config": merged, "imports": [physical]},
                        )
                    }
                )

        return (
            py2nix(
                reduce(
                    nixmerge, [emit_resource(r) for r in active_resources.values()], {}
                )
            )
            + "\n"
        )

    def get_profile(self) -> str:
        profile_dir = "/nix/var/nix/profiles/per-user/" + getpass.getuser()
        if os.path.exists(profile_dir + "/charon") and not os.path.exists(
            profile_dir + "/nixops"
        ):
            os.rename(profile_dir + "/charon", profile_dir + "/nixops")
        return profile_dir + "/nixops/" + self.uuid

    def create_profile(self) -> str:
        profile = self.get_profile()
        dir = os.path.dirname(profile)
        if not os.path.exists(dir):
            os.makedirs(dir, 0o755)
        return profile

    def build_configs(
        self,
        include: List[str],
        exclude: List[str],
        dry_run: bool = False,
        repair: bool = False,
    ) -> str:
        """Build the machine configurations in the Nix store."""

        self.logger.log("building all machine configurations...")

        # Set the NixOS version suffix, if we're building from Git.
        # That way ‘nixos-version’ will show something useful on the
        # target machines.
        #
        # TODO: Implement flake compatible version
        nixos_path = str(self.evaluate_config("nixpkgs"))
        get_version_script = nixos_path + "/modules/installer/tools/get-version-suffix"
        if os.path.exists(nixos_path + "/.git") and os.path.exists(get_version_script):
            self.nixos_version_suffix = subprocess.check_output(
                ["/bin/sh", get_version_script] + self._nix_path_flags(), text=True
            ).rstrip()

        phys_expr = self.tempdir + "/physical.nix"
        p = self.get_physical_spec()
        nixops.util.write_file(phys_expr, p)
        if DEBUG:
            print("generated physical spec:\n" + p, file=sys.stderr)

        selected = [
            m for m in self.active_machines.values() if should_do(m, include, exclude)
        ]

        names = [m.name for m in selected]

        # If we're not running on Linux, then perform the build on the
        # target machines.  FIXME: Also enable this if we're on 32-bit
        # and want to deploy to 64-bit.
        if platform.system() != "Linux" and os.environ.get("NIX_REMOTE") != "daemon":
            if os.environ.get("NIX_REMOTE_SYSTEMS") is None:
                remote_machines = []
                for m in sorted(selected, key=lambda m: m.index):
                    key_file: Optional[str] = m.get_ssh_private_key_file()
                    if not key_file:
                        raise Exception(
                            "do not know private SSH key for machine ‘{0}’".format(
                                m.name
                            )
                        )
                    # FIXME: Figure out the correct machine type of ‘m’ (it might not be x86_64-linux).
                    remote_machines.append(
                        "root@{0} {1} {2} 2 1\n".format(
                            m.get_ssh_name(), "i686-linux,x86_64-linux", key_file
                        )
                    )
                    # Use only a single machine for now (issue #103).
                    break
                remote_machines_file = "{0}/nix.machines".format(self.tempdir)
                with open(remote_machines_file, "w") as f:
                    f.write("".join(remote_machines))
                os.environ["NIX_REMOTE_SYSTEMS"] = remote_machines_file
            else:
                self.logger.log(
                    "using predefined remote systems file: {0}".format(
                        os.environ["NIX_REMOTE_SYSTEMS"]
                    )
                )

            # FIXME: Use ‘--option use-build-hook true’ instead of setting
            # $NIX_BUILD_HOOK, once Nix supports that.
            os.environ["NIX_BUILD_HOOK"] = (
                os.path.dirname(os.path.realpath(nixops.util.which("nix-build")))
                + "/../libexec/nix/build-remote.pl"
            )

            load_dir = "{0}/current-load".format(self.tempdir)
            if not os.path.exists(load_dir):
                os.makedirs(load_dir, 0o700)
            os.environ["NIX_CURRENT_LOAD"] = load_dir

        try:
            configs_path = subprocess.check_output(
                ["nix-build"]
                + self._eval_flags(self.nix_exprs + [phys_expr])
                + [
                    "--arg",
                    "names",
                    py2nix(names, inline=True),
                    "-A",
                    "machines",
                    "-o",
                    self.tempdir + "/configs",
                ]
                + (["--dry-run"] if dry_run else [])
                + (["--repair"] if repair else []),
                stderr=self.logger.log_file,
                text=True,
            ).rstrip()
        except subprocess.CalledProcessError:
            raise Exception("unable to build all machine configurations")

        if self.rollback_enabled and not dry_run:
            profile = self.create_profile()
            if subprocess.call(["nix-env", "-p", profile, "--set", configs_path]) != 0:
                raise Exception("cannot update profile ‘{0}’".format(profile))

        return configs_path

    def copy_closures(
        self,
        configs_path: str,
        include: List[str],
        exclude: List[str],
        max_concurrent_copy: int,
    ) -> None:
        """Copy the closure of each machine configuration to the corresponding machine."""

        def worker(m: nixops.backends.GenericMachineState) -> None:
            if not should_do(m, include, exclude):
                return
            m.logger.log("copying closure...")
            m.new_toplevel = os.path.realpath(configs_path + "/" + m.name)
            if not os.path.exists(m.new_toplevel):
                raise Exception("can't find closure of machine ‘{0}’".format(m.name))
            m.copy_closure_to(m.new_toplevel)

        nixops.parallel.run_tasks(
            nr_workers=max_concurrent_copy,
            tasks=iter(self.active_machines.values()),
            worker_fun=worker,
        )
        self.logger.log(
            ansi_success(
                "{0}> closures copied successfully".format(self.name or "unnamed"),
                outfile=self.logger._log_file,
            )
        )

    def activate_configs(  # noqa: C901
        self,
        configs_path: str,
        include: List[str],
        exclude: List[str],
        allow_reboot: bool,
        force_reboot: bool,
        check: bool,
        sync: bool,
        always_activate: bool,
        dry_activate: bool,
        test: bool,
        boot: bool,
        max_concurrent_activate: int,
    ) -> None:
        """Activate the new configuration on a machine."""

        def worker(m: nixops.backends.GenericMachineState) -> Optional[str]:
            if not should_do(m, include, exclude):
                return None

            def set_profile():
                # Set the system profile to the new configuration.
                daemon_var = "" if m.state == m.RESCUE else "env NIX_REMOTE=daemon "
                setprof = (
                    daemon_var + 'nix-env -p /nix/var/nix/profiles/system --set "{0}"'
                )
                defn = self._machine_definition_for_required(m.name)

                if always_activate or defn.always_activate:
                    m.run_command(setprof.format(m.new_toplevel))
                else:
                    # Only activate if the profile has changed.
                    new_profile_cmd = "; ".join(
                        [
                            'old_gen="$(readlink -f /nix/var/nix/profiles/system)"',
                            'new_gen="$(readlink -f "{0}")"',
                            '[ "x$old_gen" != "x$new_gen" ] || exit 111',
                            setprof,
                        ]
                    ).format(m.new_toplevel)

                    ret = m.run_command(new_profile_cmd, check=False)
                    if ret == 111:
                        m.log("configuration already up to date")
                        return None
                    elif ret != 0:
                        raise Exception("unable to set new system profile")

            try:
                if not test:
                    set_profile()

                m.send_keys()

                if boot or force_reboot or m.state == m.RESCUE:
                    switch_method = "boot"
                elif dry_activate:
                    switch_method = "dry-activate"
                elif test:
                    switch_method = "test"
                else:
                    switch_method = "switch"

                # Run the switch script.  This will also update the
                # GRUB boot loader.
                res = m.switch_to_configuration(
                    switch_method,
                    sync,
                    command=f"{m.new_toplevel}/bin/switch-to-configuration",
                )

                if dry_activate:
                    return None

                self.cur_flake_uri = (
                    self._get_cur_flake_uri() if self.flake_uri is not None else None
                )

                if res != 0 and res != 100:
                    raise Exception(
                        "unable to activate new configuration (exit code {})".format(
                            res
                        )
                    )

                if res == 100 or force_reboot or m.state == m.RESCUE:
                    if not allow_reboot and not force_reboot:
                        raise Exception(
                            "the new configuration requires a "
                            "reboot of '{}' to take effect (hint: use "
                            "‘--allow-reboot’)".format(m.name)
                        )
                    m.reboot_sync()
                    res = 0
                    # FIXME: should check which systemd services
                    # failed to start after the reboot.

                if res == 0:
                    m.success("activation finished successfully")

                # Record that we switched this machine to the new
                # configuration.
                m.cur_configs_path = configs_path
                m.cur_toplevel = m.new_toplevel
                m.cur_flake_uri = (
                    self._get_cur_flake_uri() if self.flake_uri is not None else None
                )

            except Exception:
                # This thread shouldn't throw an exception because
                # that will cause NixOps to exit and interrupt
                # activation on the other machines.
                m.logger.error(traceback.format_exc())
                return m.name
            return None

        res = nixops.parallel.run_tasks(
            nr_workers=max_concurrent_activate,
            tasks=iter(self.active_machines.values()),
            worker_fun=worker,
        )
        failed = [x for x in res if x is not None]
        if failed != []:
            raise Exception(
                "activation of {0} of {1} machines failed (namely on {2})".format(
                    len(failed),
                    len(res),
                    ", ".join(["‘{0}’".format(x) for x in failed]),
                )
            )

    def _get_free_resource_index(self) -> int:
        index = 0
        for r in self.resources.values():
            if r.index is not None and index <= r.index:
                index = r.index + 1
        return index

    def get_backups(
        self, include: List[str] = [], exclude: List[str] = []
    ) -> Dict[str, Dict[str, Any]]:
        self.evaluate_active(include, exclude)  # unnecessary?
        machine_backups = {}
        for m in self.active_machines.values():
            if should_do(m, include, exclude):
                machine_backups[m.name] = m.get_backups()

        # merging machine backups into network backups
        backup_ids = [b for bs in machine_backups.values() for b in bs.keys()]

        backups: Dict[str, Dict[str, Any]] = {}
        for backup_id in backup_ids:
            backups[backup_id] = {}
            backups[backup_id]["machines"] = {}
            backups[backup_id]["info"] = []
            backups[backup_id]["status"] = "complete"
            backup = backups[backup_id]
            for m in self.active_machines.values():
                if should_do(m, include, exclude):
                    if backup_id in machine_backups[m.name].keys():
                        backup["machines"][m.name] = machine_backups[m.name][backup_id]
                        backup["info"].extend(backup["machines"][m.name]["info"])
                        # status is always running when one of the backups is still running
                        if (
                            backup["machines"][m.name]["status"] != "complete"
                            and backup["status"] != "running"
                        ):
                            backup["status"] = backup["machines"][m.name]["status"]
                    else:
                        backup["status"] = "incomplete"
                        backup["info"].extend(
                            ["No backup available for {0}".format(m.name)]
                        )

        return backups

    def clean_backups(
        self, keep: bool, keep_days: int, keep_physical: bool = False
    ) -> None:
        _backups = self.get_backups()
        backup_ids = sorted(_backups.keys())

        if keep:
            index = len(backup_ids) - keep
            tbr = backup_ids[:index]

        if keep_days:
            cutoff = (datetime.now() - timedelta(days=keep_days)).strftime(
                "%Y%m%d%H%M%S"
            )
            print(cutoff)
            tbr = [bid for bid in backup_ids if bid < cutoff]

        for backup_id in tbr:
            print("Removing backup {0}".format(backup_id))
            self.remove_backup(backup_id, keep_physical)

    def remove_backup(self, backup_id: str, keep_physical: bool = False) -> None:
        with self._get_deployment_lock():

            def worker(m: nixops.backends.GenericMachineState) -> None:
                m.remove_backup(backup_id, keep_physical)

            nixops.parallel.run_tasks(
                nr_workers=len(self.active_machines),
                tasks=iter(self.machines.values()),
                worker_fun=worker,
            )

    def backup(
        self, include: List[str] = [], exclude: List[str] = [], devices: List[str] = []
    ) -> str:
        self.evaluate_active(include, exclude)
        backup_id = datetime.now().strftime("%Y%m%d%H%M%S")

        def worker(m: nixops.backends.GenericMachineState) -> None:
            if not should_do(m, include, exclude):
                return
            if m.state != m.STOPPED:
                ssh_name = m.get_ssh_name()
                res = subprocess.call(
                    ["ssh", "root@" + ssh_name] + m.get_ssh_flags() + ["sync"]
                )
                if res != 0:
                    m.logger.log("running sync failed on {0}.".format(m.name))
            m.backup(self._machine_definition_for_required(m.name), backup_id, devices)

        nixops.parallel.run_tasks(
            nr_workers=5, tasks=iter(self.active_machines.values()), worker_fun=worker
        )

        return backup_id

    def restore(
        self,
        include: List[str] = [],
        exclude: List[str] = [],
        backup_id: Optional[str] = None,
        devices: List[str] = [],
    ) -> None:
        with self._get_deployment_lock():

            self.evaluate_active(include, exclude)

            def worker(m: nixops.backends.GenericMachineState) -> None:
                if not should_do(m, include, exclude):
                    return
                m.restore(
                    self._machine_definition_for_required(m.name), backup_id, devices
                )

            nixops.parallel.run_tasks(
                nr_workers=-1,
                tasks=iter(self.active_machines.values()),
                worker_fun=worker,
            )
            self.start_machines(include=include, exclude=exclude)
            self.logger.warn(
                "restore finished; please note that you might need to run ‘nixops deploy’ to fix configuration issues regarding changed IP addresses"
            )

    def evaluate_active(
        self,
        include: List[str] = [],
        exclude: List[str] = [],
        kill_obsolete: bool = False,
    ) -> None:
        self.evaluate()

        # Create state objects for all defined resources.
        with self._db:
            for defn in self._definitions().values():
                if defn.name not in self.resources:
                    self._create_resource(defn.name, defn.get_type())

        self.logger.update_log_prefixes()

        to_destroy = []

        # Determine the set of active resources.  (We can't just
        # delete obsolete resources from ‘self.resources’ because they
        # contain important state that we don't want to forget about.)
        for m in self.resources.values():
            if m.name in self._definitions():
                if m.obsolete:
                    self.logger.log(
                        "resource ‘{0}’ is no longer obsolete".format(m.name)
                    )
                    m.obsolete = False
            else:
                self.logger.log("resource ‘{0}’ is obsolete".format(m.name))
                if not m.obsolete:
                    m.obsolete = True
                if not should_do(m, include, exclude):
                    continue
                if kill_obsolete:
                    to_destroy.append(m.name)

        if to_destroy:
            self._destroy_resources(include=to_destroy)

    def _deploy(  # noqa: C901
        self,
        dry_run: bool = False,
        test: bool = False,
        boot: bool = False,
        plan_only: bool = False,
        build_only: bool = False,
        create_only: bool = False,
        copy_only: bool = False,
        include: List[str] = [],
        exclude: List[str] = [],
        check: bool = False,
        kill_obsolete: bool = False,
        allow_reboot: bool = False,
        allow_recreate: bool = False,
        force_reboot: bool = False,
        max_concurrent_copy: int = 5,
        max_concurrent_activate: int = -1,
        sync: bool = True,
        always_activate: bool = False,
        repair: bool = False,
        dry_activate: bool = False,
    ) -> None:
        """Perform the deployment defined by the deployment specification."""

        self.evaluate_active(include, exclude, kill_obsolete)

        # Assign each resource an index if it doesn't have one.
        for r in self.active_resources.values():
            if r.index is None:
                r.index = self._get_free_resource_index()
                # FIXME: Logger should be able to do coloring without the need
                #        for an index maybe?
                r.logger.register_index(r.index)

        self.logger.update_log_prefixes()

        # Start or update the active resources.  Non-machine resources
        # are created first, because machines may depend on them
        # (e.g. EC2 machines depend on EC2 key pairs or EBS volumes).
        # FIXME: would be nice to have a more fine-grained topological
        # sort.
        if not dry_run and not build_only:

            for r in self.active_resources.values():
                defn = self._definition_for_required(r.name)
                if r.get_type() != defn.get_type():
                    raise Exception(
                        "the type of resource ‘{0}’ changed from ‘{1}’ to ‘{2}’, which is currently unsupported".format(
                            r.name, r.get_type(), defn.get_type()
                        )
                    )
                r._created_event = threading.Event()
                r._errored = False

            def plan_worker(r: nixops.resources.DiffEngineResourceState) -> None:
                if not should_do(r, include, exclude):
                    return
                r.plan(self._definition_for_required(r.name))

            if plan_only:
                for r in self.active_resources.values():
                    if isinstance(r, nixops.resources.DiffEngineResourceState):
                        plan_worker(r)
                    else:
                        r.warn(
                            "resource type {} doesn't implement a plan operation".format(
                                r.get_type()
                            )
                        )

                return

            def worker(r: nixops.resources.GenericResourceState):
                try:
                    if not should_do(r, include, exclude):
                        return

                    # Sleep until all dependencies of this resource have
                    # been created.
                    deps = r.create_after(
                        iter(self.active_resources.values()),
                        self._definition_for_required(r.name),
                    )
                    for dep in deps:
                        if dep._created_event:
                            dep._created_event.wait()
                        # !!! Should we print a message here?
                        if dep._errored:
                            r._errored = True
                            return

                    # Now create the resource itself.
                    if not r.creation_time:
                        r.creation_time = int(time.time())
                    r.create(
                        self._definition_for_required(r.name),
                        check=check,
                        allow_reboot=allow_reboot,
                        allow_recreate=allow_recreate,
                    )

                    if is_machine(r):
                        # NOTE: unfortunate mypy doesn't check that
                        # is_machine calls an isinstance() function
                        m = cast(nixops.backends.GenericMachineState, r)
                        # The first time the machine is created,
                        # record the state version. We get it from
                        # /etc/os-release, rather than from the
                        # configuration's state.systemVersion
                        # attribute, because the machine may have been
                        # booted from an older NixOS image.
                        if not m.state_version:
                            os_release = m.run_command(
                                "cat /etc/os-release", capture_stdout=True
                            )
                            match = re.search(
                                'VERSION_ID="([0-9]+\.[0-9]+).*"',  # noqa: W605
                                os_release,
                            )
                            if match:
                                m.state_version = match.group(1)
                                m.log(
                                    "setting state version to {0}".format(
                                        m.state_version
                                    )
                                )
                            else:
                                m.warn("cannot determine NixOS version")

                        m.wait_for_ssh(check=check)

                        MachineHooksManager.post_wait(m)

                except Exception:
                    r._errored = True
                    raise
                finally:
                    if r._created_event:
                        r._created_event.set()

            nixops.parallel.run_tasks(
                nr_workers=-1,
                tasks=iter(self.active_resources.values()),
                worker_fun=worker,
            )

        if create_only:
            return

        # Build the machine configurations.
        # Record configs_path in the state so that the ‘info’ command
        # can show whether machines have an outdated configuration.
        self.configs_path = self.build_configs(
            dry_run=dry_run, repair=repair, include=include, exclude=exclude
        )

        if build_only or dry_run:
            return

        # Copy the closures of the machine configurations to the
        # target machines.
        self.copy_closures(
            self.configs_path,
            include=include,
            exclude=exclude,
            max_concurrent_copy=max_concurrent_copy,
        )

        if copy_only:
            return

        # Active the configurations.
        self.activate_configs(
            self.configs_path,
            include=include,
            exclude=exclude,
            allow_reboot=allow_reboot,
            force_reboot=force_reboot,
            check=check,
            sync=sync,
            always_activate=always_activate,
            dry_activate=dry_activate,
            test=test,
            boot=boot,
            max_concurrent_activate=max_concurrent_activate,
        )

        if dry_activate:
            return

        # Trigger cleanup of resources, e.g. disks that need to be detached etc. Needs to be
        # done after activation to make sure they are not in use anymore.
        def cleanup_worker(r: nixops.resources.GenericResourceState) -> None:
            if not should_do(r, include, exclude):
                return

            # Now create the resource itself.
            r.after_activation(self._definition_for_required(r.name))

        nixops.parallel.run_tasks(
            nr_workers=-1,
            tasks=iter(self.active_resources.values()),
            worker_fun=cleanup_worker,
        )
        self.logger.log(
            ansi_success(
                "{0}> deployment finished successfully".format(self.name or "unnamed"),
                outfile=self.logger._log_file,
            )
        )

    # can generalize notifications later (e.g. emails, for now just hardcode datadog)
    def notify_start(self, action: str) -> None:
        self.evaluate_network(action)

    def notify_success(self, action: str) -> None:
        pass

    def notify_failed(
        self, action: str, e: Union[KeyboardInterrupt, Exception]
    ) -> None:
        pass

    def run_with_notify(self, action: str, f: Callable[[], None]) -> None:
        self.notify_start(action)
        try:
            f()
            self.notify_success(action)
        except KeyboardInterrupt as e:
            self.notify_failed(action, e)
            raise
        except Exception as e:
            self.notify_failed(action, e)
            raise

    def deploy(self, **kwargs: Any) -> None:
        with self._get_deployment_lock():
            self.run_with_notify("deploy", lambda: self._deploy(**kwargs))

    def _rollback(
        self,
        generation: int,
        include: List[str] = [],
        exclude: List[str] = [],
        check: bool = False,
        allow_reboot: bool = False,
        force_reboot: bool = False,
        max_concurrent_copy: int = 5,
        max_concurrent_activate: int = -1,
        sync: bool = True,
    ) -> None:
        if not self.rollback_enabled:
            raise Exception(
                "rollback is not enabled for this network; please set ‘network.enableRollback’ to ‘true’ and redeploy"
            )
        profile = self.get_profile()
        if (
            subprocess.call(
                ["nix-env", "-p", profile, "--switch-generation", str(generation)]
            )
            != 0
        ):
            raise Exception("nix-env --switch-generation failed")

        self.configs_path = os.path.realpath(profile)
        assert os.path.isdir(self.configs_path)

        names = set()
        for filename in os.listdir(self.configs_path):
            if not os.path.islink(self.configs_path + "/" + filename):
                continue
            if (
                should_do_n(filename, include, exclude)
                and filename not in self.machines
            ):
                raise Exception(
                    "cannot roll back machine ‘{0}’ which no longer exists".format(
                        filename
                    )
                )
            names.add(filename)

        # Update the set of active machines.
        for m in self.machines.values():
            if m.name in names:
                if m.obsolete:
                    self.logger.log(
                        "machine ‘{0}’ is no longer obsolete".format(m.name)
                    )
                    m.obsolete = False
            else:
                self.logger.log("machine ‘{0}’ is obsolete".format(m.name))
                m.obsolete = True

        self.copy_closures(
            self.configs_path,
            include=include,
            exclude=exclude,
            max_concurrent_copy=max_concurrent_copy,
        )

        self.activate_configs(
            self.configs_path,
            include=include,
            exclude=exclude,
            allow_reboot=allow_reboot,
            force_reboot=force_reboot,
            check=check,
            sync=sync,
            always_activate=True,
            dry_activate=False,
            test=False,
            boot=False,
            max_concurrent_activate=max_concurrent_activate,
        )

        self.cur_flake_uri = None

    def rollback(self, **kwargs: Any) -> None:
        with self._get_deployment_lock():
            self._rollback(**kwargs)

    def _destroy_resources(
        self, include: List[str] = [], exclude: List[str] = [], wipe: bool = False
    ) -> None:

        for r in self.resources.values():
            r._destroyed_event = threading.Event()
            r._errored = False
            for rev_dep in r.destroy_before(iter(self.resources.values())):
                try:
                    rev_dep._wait_for.append(r)
                except AttributeError:
                    rev_dep._wait_for = [r]

        def worker(m: nixops.resources.GenericResourceState) -> None:
            try:
                if not should_do(m, include, exclude):
                    return
                try:
                    for dep in m._wait_for:
                        if dep._created_event:
                            dep._created_event.wait()
                        # !!! Should we print a message here?
                        if dep._errored:
                            m._errored = True
                            return
                except AttributeError:
                    pass
                if m.destroy(wipe=wipe):
                    self.delete_resource(m)
            except Exception:
                m._errored = True
                raise
            finally:
                if m._destroyed_event:
                    m._destroyed_event.set()

        nixops.parallel.run_tasks(
            nr_workers=-1, tasks=list(self.resources.values()), worker_fun=worker
        )

    def destroy_resources(
        self, include: List[str] = [], exclude: List[str] = [], wipe: bool = False
    ) -> None:
        """Destroy all active and obsolete resources."""

        with self._get_deployment_lock():
            self.run_with_notify(
                "destroy", lambda: self._destroy_resources(include, exclude, wipe)
            )

        # Remove the destroyed machines from the rollback profile.
        # This way, a subsequent "nix-env --delete-generations old" or
        # "nix-collect-garbage -d" will get rid of the machine
        # configurations.
        if self.rollback_enabled:  # and len(self.active) == 0:
            profile = self.create_profile()
            attrs = {
                m.name: Call(RawValue("builtins.storePath"), m.cur_toplevel)
                for m in self.active_machines.values()
                if m.cur_toplevel
            }
            if (
                subprocess.call(
                    [
                        "nix-env",
                        "-p",
                        profile,
                        "--set",
                        "*",
                        "-I",
                        "nixops=" + self.expr_path,
                        "-f",
                        "<nixops/update-profile.nix>",
                        "--arg",
                        "machines",
                        py2nix(attrs, inline=True),
                    ]
                )
                != 0
            ):
                raise Exception("cannot update profile ‘{0}’".format(profile))

    def delete_resources(
        self, include: List[str] = [], exclude: List[str] = []
    ) -> None:
        """delete all resources state."""

        def worker(m: nixops.resources.GenericResourceState) -> None:
            if not should_do(m, include, exclude):
                return
            if m.delete_resources():
                self.delete_resource(m)

        nixops.parallel.run_tasks(
            nr_workers=-1, tasks=list(self.resources.values()), worker_fun=worker
        )

    def reboot_machines(
        self,
        include: List[str] = [],
        exclude: List[str] = [],
        wait: bool = False,
        rescue: bool = False,
        hard: bool = False,
    ) -> None:
        """Reboot all active machines."""

        def worker(m: nixops.backends.GenericMachineState) -> None:
            if not should_do(m, include, exclude):
                return
            if rescue:
                m.reboot_rescue(hard=hard)
            elif wait:
                m.reboot_sync(hard=hard)
            else:
                m.reboot(hard=hard)

        nixops.parallel.run_tasks(
            nr_workers=-1, tasks=iter(self.active_machines.values()), worker_fun=worker
        )

    def stop_machines(self, include: List[str] = [], exclude: List[str] = []) -> None:
        """Stop all active machines."""

        def worker(m: nixops.backends.GenericMachineState) -> None:
            if not should_do(m, include, exclude):
                return
            m.stop()

        nixops.parallel.run_tasks(
            nr_workers=-1, tasks=iter(self.active_machines.values()), worker_fun=worker
        )

    def start_machines(self, include: List[str] = [], exclude: List[str] = []) -> None:
        """Start all active machines."""

        def worker(m: nixops.backends.GenericMachineState) -> None:
            if not should_do(m, include, exclude):
                return
            m.start()

        nixops.parallel.run_tasks(
            nr_workers=-1, tasks=iter(self.active_machines.values()), worker_fun=worker
        )

    def is_valid_resource_name(self, name: str) -> bool:
        p = re.compile("^[\w-]+$")  # noqa: W605
        return not p.match(name) is None

    def rename(self, name: str, new_name: str) -> None:
        if name not in self.resources:
            raise Exception("resource ‘{0}’ not found".format(name))
        if new_name in self.resources:
            raise Exception("resource with name ‘{0}’ already exists".format(new_name))
        if not self.is_valid_resource_name(new_name):
            raise Exception("{0} is not a valid resource identifier".format(new_name))

        self.logger.log("renaming resource ‘{0}’ to ‘{1}’...".format(name, new_name))

        m = self.resources.pop(name)
        self.resources[new_name] = m

        with self._db:
            self._db.execute(
                "update Resources set name = ? where deployment = ? and id = ?",
                (new_name, self.uuid, m.id),
            )

    def send_keys(self, include: List[str] = [], exclude: List[str] = []) -> None:
        """Send encryption keys to machines."""

        def worker(m: nixops.backends.GenericMachineState) -> None:
            if not should_do(m, include, exclude):
                return
            m.send_keys()

        nixops.parallel.run_tasks(
            nr_workers=-1, tasks=iter(self.active_machines.values()), worker_fun=worker
        )


def should_do(
    m: Union[
        nixops.resources.GenericResourceState, nixops.backends.GenericMachineState
    ],
    include: List[str],
    exclude: List[str],
) -> bool:
    return should_do_n(m.name, include, exclude)


def should_do_n(name: str, include: List[str], exclude: List[str]) -> bool:
    if name in exclude:
        return False
    if include == []:
        return True
    return name in include


def is_machine(
    r: Union[nixops.resources.GenericResourceState, nixops.backends.GenericMachineState]
) -> bool:
    # Hack around isinstance checks not working on subscripted generics
    # See ./monkey.py
    return nixops.backends.MachineState in r.__class__.mro()


def _filter_machines(
    resources: Dict[str, nixops.resources.GenericResourceState]
) -> Dict[str, nixops.backends.GenericMachineState]:
    return {
        n: r  # type: ignore
        for n, r in resources.items()
        if is_machine(r)
    }


def is_machine_defn(r: nixops.resources.GenericResourceState) -> bool:
    return isinstance(r, nixops.backends.MachineDefinition)


def _subclasses(cls: Any) -> List[Any]:
    sub = cls.__subclasses__()
    return [cls] if not sub else [g for s in sub for g in _subclasses(s)]


def _create_definition(
    name: str, config: Dict[str, Any], type_name: str
) -> nixops.resources.ResourceDefinition:
    """Create a resource definition object from the given XML representation of the machine's attributes."""

    for cls in _subclasses(nixops.resources.ResourceDefinition):
        if type_name == cls.get_resource_type():
            return cls(name, nixops.resources.ResourceEval(config))

    raise nixops.deployment.UnknownBackend(
        "unknown resource type ‘{0}’".format(type_name)
    )


def _create_state(depl: Deployment, type: str, name: str, id: int) -> Any:
    """Create a resource state object of the desired type."""

    for cls in _subclasses(nixops.resources.ResourceState):
        try:
            if type == cls.get_type():
                return cls(depl, name, id)
        except NotImplementedError:
            pass

    raise nixops.deployment.UnknownBackend("unknown resource type ‘{0}’".format(type))


# Automatically load all resource types.
def _load_modules_from(dir: str) -> None:
    for module in os.listdir(os.path.dirname(__file__) + "/" + dir):
        if module[-3:] != ".py" or module == "__init__.py":
            continue
        importlib.import_module("nixops." + dir + "." + module[:-3])


_load_modules_from("backends")
_load_modules_from("resources")
