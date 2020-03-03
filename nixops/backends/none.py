# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from typing import Any, Optional, List, Dict, Tuple, Union
import xml.etree.ElementTree as ET

from nixops.backends import MachineDefinition, MachineState
import nixops.deployment
import nixops.resources
import nixops.util
from nixops.util import attr_property, create_key_pair


class NoneDefinition(MachineDefinition):
    """Definition of a trivial machine."""

    @classmethod
    def get_type(cls) -> str:
        return "none"

    def __init__(self, xml: ET.Element, config: Dict[str, Any]) -> None:
        MachineDefinition.__init__(self, xml, config)
        self._target_host = nixops.util.xml_find_get(
            xml, "attrs/attr[@name='targetHost']/string"
        )
        self._public_ipv4 = nixops.util.xml_find_get(
            xml, "attrs/attr[@name='publicIPv4']/string"
        )


class NoneState(MachineState):
    """State of a trivial machine."""

    @classmethod
    def get_type(cls) -> str:
        return "none"

    target_host: Optional[str] = attr_property("targetHost", None)
    public_ipv4: Optional[str] = attr_property("publicIpv4", None)
    _ssh_private_key: Optional[str] = attr_property("none.sshPrivateKey", None)
    _ssh_public_key: Optional[str] = attr_property("none.sshPublicKey", None)
    _ssh_public_key_deployed: bool = attr_property(
        "none.sshPublicKeyDeployed", False, bool
    )

    def __init__(self, depl: nixops.deployment.Deployment, name: str, id: str) -> None:
        MachineState.__init__(self, depl, name, id)

    @property
    def resource_id(self) -> Optional[str]:
        return self.vm_id

    def get_physical_spec(self) -> Dict[Union[Tuple[str, ...], str], Any]:
        return (
            {
                (
                    "config",
                    "users",
                    "extraUsers",
                    "root",
                    "openssh",
                    "authorizedKeys",
                    "keys",
                ): [self._ssh_public_key]
            }
            if self._ssh_public_key
            else {}
        )

    def create(
        self,
        defn: nixops.resources.ResourceDefinition,
        check: bool,
        allow_reboot: bool,
        allow_recreate: bool,
    ) -> None:
        assert isinstance(defn, NoneDefinition)
        self.set_common_state(defn)
        self.target_host = defn._target_host
        self.public_ipv4 = defn._public_ipv4

        if not self.vm_id:
            self.logger.log_start("generating new SSH keypair... ")
            key_name = "NixOps client key for {0}".format(self.name)
            self._ssh_private_key, self._ssh_public_key = create_key_pair(
                key_name=key_name
            )
            self.logger.log_end("done")
            self.vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)

    def switch_to_configuration(
        self, method: str, sync: bool, command: Optional[str] = None
    ) -> int:
        res = super(NoneState, self).switch_to_configuration(method, sync, command)
        if res == 0:
            self._ssh_public_key_deployed = True
        return res

    def get_ssh_name(self) -> str:
        assert self.target_host
        return self.target_host

    def get_ssh_private_key_file(self) -> Optional[str]:
        if self._ssh_private_key_file:
            return self._ssh_private_key_file
        elif self._ssh_private_key:
            return self.write_ssh_private_key(self._ssh_private_key)
        else:
            # TODO: make better message
            raise Exception("No SSH key available")

    def get_ssh_flags(self, scp: bool = False) -> List[str]:
        super_state_flags = super(NoneState, self).get_ssh_flags(scp=scp)

        ssh_private_key_file = self.get_ssh_private_key_file()
        assert ssh_private_key_file is not None

        if self.vm_id and self.cur_toplevel and self._ssh_public_key_deployed:
            return super_state_flags + [
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-i",
                ssh_private_key_file,
            ]
        return super_state_flags

    # FIXME: see _check in MachineState for fixing type
    def _check(self, res: nixops.backends.CheckResult) -> None:  # type: ignore
        if not self.vm_id:
            res.exists = False
            return
        res.exists = True
        assert self.target_host
        res.is_up = nixops.util.ping_tcp_port(self.target_host, self.ssh_port)
        if res.is_up:
            MachineState._check(self, res)

    def destroy(self, wipe: bool = False) -> bool:
        # No-op; just forget about the machine.
        return True
