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

    @classmethod
    def get_resource_type(cls):
        return "gceStaticIPs"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.addr_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'region', str)

        self.copy_option(xml,'ipAddress',str, optional = True)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCEStaticIPState(ResourceState):
    """State of a GCE Static IP"""

    region = attr_property("gce.region", None)
    addr_name = attr_property("gce.name", None)
    ip_address = attr_property("gce.ipAddress", None)

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
        return "GCE static IP address '{0}'".format(self.addr_name)

    def address(self):
        return self.connect().ex_get_address(self.addr_name, region=self.region)

    @property
    def public_ipv4(self):
        return self.ip_address

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(defn.ip_address and self.ip_address != defn.ip_address, 'address')
        self.no_project_change(defn)
        self.no_region_change(defn)

        self.copy_credentials(defn)
        self.addr_name = defn.addr_name

        if check:
            try:
                address = self.address()
                if self.state == self.UP:
                    self.handle_changed_property('ip_address', address.address, property_name = '')
                    self.handle_changed_property('region', address.region.name, can_fix = False)
                else:
                    self.warn_not_supposed_to_exist(valuable_resource = True)
                    self.confirm_destroy(address, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log("reserving {0} in {1}...".format(self.full_name, defn.region))
            try:
                address = self.connect().ex_create_address(defn.addr_name, region = defn.region,
                                                           address = defn.ip_address)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("tried requesting a static IP that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("reserved IP address: {0}".format(address.address))
            self.state = self.UP
            self.region = defn.region
            self.ip_address = address.address;


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                address = self.address()
                return self.confirm_destroy(address, "{0} ({1})".format(self.full_name, self.ip_address), abort = False)
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
        return True
