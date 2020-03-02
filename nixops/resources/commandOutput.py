# -*- coding: utf-8 -*-

# Arbitrary JSON.

import os
import nixops.util
import nixops.resources

import tempfile
import shutil
import subprocess
import hashlib


# For typing
from nixops.deployment import Deployment
from xml.etree.ElementTree import Element
from nixops.nix_expr import Function
from typing import Any, Optional, List, Dict, Tuple, Union


class CommandOutputDefinition(nixops.resources.ResourceDefinition):
    """Definition of a Command Output."""

    @classmethod
    def get_type(cls) -> str:
        return "command-output"

    @classmethod
    def get_resource_type(cls) -> str:
        return "commandOutput"

    def show_type(self) -> str:
        return "{0}".format(self.get_type())


class CommandOutputState(nixops.resources.ResourceState):
    """State of a Command Output."""

    state = nixops.util.attr_property(
        "state", nixops.resources.ResourceState.MISSING, int
    )
    script = nixops.util.attr_property("script", None)
    value = nixops.util.attr_property("value", None)
    commandName = nixops.util.attr_property("name", None)

    @classmethod
    def get_type(cls) -> str:
        return "command-output"

    @property
    def resource_id(self) -> Optional[str]:
        if self.value is not None:
            # Avoid printing any potential secret information
            return "{0}-{1}".format(
                self.commandName, hashlib.sha256(self.value).hexdigest()[:32]
            )
        else:
            return None

    def create(
        self,
        defn: nixops.resources.ResourceDefinition,
        check: bool,
        allow_reboot: bool,
        allow_recreate: bool,
    ) -> None:
        if (
            (defn.config["script"] is not None)
            and (self.script != defn.config["script"])
            or self.value is None
        ):
            self.commandName = defn.name
            try:
                output_dir = nixops.util.SelfDeletingDir(
                    tempfile.mkdtemp(prefix="nixops-output-tmp")
                )

                self.logger.log(
                    "Running shell function for output ‘{0}’...".format(defn.name)
                )
                env = {}  # type: Dict[str,str]
                env.update(os.environ)
                env.update({"out": output_dir})
                res = subprocess.check_output(
                    [defn.config["script"]], env=env, shell=True, text=True
                )
                with self.depl._db:
                    self.value = res
                    self.state = self.UP
                    self.script = defn.config["script"]
            except Exception as e:
                self.logger.log("Creation failed for output ‘{0}’...".format(defn.name))
                raise

    def prefix_definition(self, attr: Dict[Any, Any]) -> Dict[Any, Any]:
        # (Dict[str,Function]) -> Dict[Tuple[str,str],Dict[str,Function]]
        return {("resources", "commandOutput"): attr}

    def get_physical_spec(self) -> Dict[Union[Tuple[str, ...], str], Any]:
        return {"value": self.value}

    def destroy(self, wipe: bool = False) -> bool:
        if self.depl.logger.confirm(
            "are you sure you want to destroy {0}?".format(self.name)
        ):
            self.logger.log("destroying...")
        else:
            raise Exception("can't proceed further")

        self.value = None
        self.state = self.MISSING
        return True
