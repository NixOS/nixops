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
from typing import Optional, List, Dict, Tuple

class OutputDefinition(nixops.resources.ResourceDefinition):
    """Definition of an Output."""

    @classmethod
    def get_type(cls):
        # type: () -> (str)
        return "output"

    @classmethod
    def get_resource_type(cls):
        # type: () -> (str)
        return "output"

    def show_type(self):
        # type: () -> (str)
        return "{0}".format(self.get_type())

class OutputState(nixops.resources.ResourceState):
    """State of an output."""
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    script = nixops.util.attr_property("script",None)
    value = nixops.util.attr_property("value",None)
    outputName =  nixops.util.attr_property("name",None)

    @classmethod
    def get_type(cls):
        # type: () -> (str)
        return "output"

    @property
    def resource_id(self):
        # type: () -> Optional[str]
        if self.value is not None:
            # Avoid printing any potential secret information
            return "{0}-{1}".format(self.outputName,hashlib.sha256(self.value).hexdigest()[:32])
        else:
            return None

    def create(self, defn, check, allow_reboot, allow_recreate):
        # type: (OutputDefinition,bool,bool,bool) -> None
        if (defn.config['script'] is not None ) and (self.script != defn.config['script']) or self.value is None:
            self.outputName = defn.name
            try:
                output_dir = nixops.util.SelfDeletingDir(tempfile.mkdtemp(prefix="nixops-output-tmp"))

                self.log("Running shell function for output ‘{0}’...".format(defn.name))
                env = {} # type: Dict[str,str]
                env.update(os.environ)
                env.update({"out":output_dir})
                res = subprocess.check_output(
                        [defn.config['script']],
                        env=env,
                        shell=True)
                with self.depl._db:
                    self.value = res
                    self.state = self.UP
                    self.script = defn.config['script']
            except Exception as e:
                self.log("Creation failed for output ‘{0}’...".format(defn.name))
                raise

    def prefix_definition(self, attr):
        # type: (Dict[str,Function]) -> Dict[Tuple[str,str],Dict[str,Function]]
        return {('resources', 'output'): attr}

    def get_physical_spec(self):
        # type: () -> Dict[str,str]
        return {'value': self.value}

    def destroy(self, wipe=False):
        # type: (bool) -> bool
        if self.depl.logger.confirm("are you sure you want to destroy {0}?".format(self.outputName)):
            self.log("destroying...")
        else:
            raise Exception("can't proceed further")
        self.value = None
        self.state = self.MISSING
        return True
