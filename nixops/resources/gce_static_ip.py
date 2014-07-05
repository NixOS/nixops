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

    nix_name = "gceStaticIPs"

    @property
    def full_name(self):
        return "GCE Static IP Address '{0}'".format(self.addr_name)

    def address(self):
        return self.connect().ex_get_address(self.addr_name, region=self.region)

    @property
    def public_ipv4(self):
        return self.ipAddress

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(defn.ipAddress and self.ipAddress != defn.ipAddress, 'address')
        self.no_project_change(defn)
        self.no_region_change(defn)

        self.copy_credentials(defn)
        self.addr_name = defn.addr_name

        if check:
            try:
                address = self.address()
                if self.state == self.UP:
                    self.ipAddress = self.warn_if_changed(self.ipAddress, address.address, '')
                    self.warn_if_changed(self.region, address.region.name,
                                         'region', can_fix = False)
                else:
                    self.warn_not_supposed_to_exist(valuable_resource = True)
                    self.confirm_destroy(address, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log_start("Requesting {0} in {1}...".format(self.full_name, defn.region))
            try:
                address = self.connect().ex_create_address(defn.addr_name, region = defn.region,
                                                           address = defn.ipAddress)
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
                return self.confirm_destroy(address, "{0} ({1})".format(self.full_name, self.ipAddress), abort = False)
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy {0} which didn't exist".format(self.full_name))
        return True
