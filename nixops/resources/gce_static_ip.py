# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Static/Reserved IP addresses.

import os
import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string


class GCEStaticIPDefinition(ResourceDefinition):
    """Definition of a GCE Static IP"""

    @classmethod
    def get_type(cls):
        return "gce-static-ip"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.addr_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")

        self.ipAddress = optional_string(xml.find("attrs/attr[@name='ipAddress']/string"))

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCEStaticIPState(ResourceState):
    """State of a GCE Static IP"""

    region = attr_property("gce.region", None)
    addr_name = attr_property("gce.name", None)
    ipAddress = attr_property("gce.ipAddress", None)

    @classmethod
    def get_type(cls):
        return "gce-static-ip"


    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GCEStaticIPState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s


    @property
    def resource_id(self):
        return self.addr_name

    def nix_name(self):
        return "gceStaticIPs"

    def address(self):
        return self.connect().ex_get_address(self.addr_name, region=self.region)

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if self.project != defn.project:
                raise Exception("cannot change the project of a deployed GCE static IP")

            if self.region != defn.region:
                raise Exception("cannot change the region of a deployed GCE static IP")

            if defn.ipAddress and self.ipAddress != defn.ipAddress:
                raise Exception("cannot change address of a deployed GCE static IP")

        self.copy_credentials(defn)
        self.addr_name = defn.addr_name

        if check:
            try:
                address = self.address()
                if self.state == self.UP:
                    if self.ipAddress != address.address:
                        self.warn("GCE static IP ‘{0}’ has changed to {1}. Expected it to be {2}".
                                  format(defn.addr_name, address.address, self.ipAddress))
                else:
                    raise Exception("GCE static IP ‘{0}’ exists, but isn't supposed to. Probably, this is the result "
                                    "of a botched creation attempt and can be fixed by deletion.".
                                    format(defn.addr_name))
            except libcloud.common.google.ResourceNotFoundError:
                if self.state == self.UP:
                    self.warn("GCE static IP ‘{0}’ is supposed to exist, but is missing. Recreating...".format(defn.addr_name))
                    self.state = self.MISSING

        if self.state != self.UP:
            self.log_start("Requesting GCE static IP ‘{0}’ in {1}...".format(defn.addr_name, defn.region))
            try:
                address = self.connect().ex_create_address(defn.addr_name, region = defn.region)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried requesting a static IP that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end("done.")
            self.log("Reserved IP address: {0}".format(address.address))
            
            self.state = self.UP
            self.region = defn.region
            self.ipAddress = address.address;


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                address = self.address()
                if not self.depl.logger.confirm("are you sure you want to destroy GCE static IP ‘{0}’({1})?".format(self.addr_name, self.ipAddress)):
                    return False
                self.log("releasing GCE static IP ‘{0}’...".format(self.addr_name))
                address.destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy GCE static IP ‘{0}’ which didn't exist".format(self.addr_name))
        return True
