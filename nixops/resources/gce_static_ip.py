# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Static/Reserved IP addresses.

import os
import libcloud.common.google
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

from nixops.util import attr_property
import nixops.resources


class GCEStaticIPDefinition(nixops.resources.ResourceDefinition):
    """Definition of a GCE Static IP"""

    @classmethod
    def get_type(cls):
        return "gce-static-ip"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)

        self.addr_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")

        addr = xml.find("attrs/attr[@name='ipAddress']/string")
        self.ipAddress = ( addr.get("value") if addr is not None else None )

        # FIXME: factor this out
        self.project = xml.find("attrs/attr[@name='project']/string").get("value")
        self.service_account = xml.find("attrs/attr[@name='serviceAccount']/string").get("value")
        self.access_key_path = xml.find("attrs/attr[@name='accessKey']/string").get("value")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCEStaticIPState(nixops.resources.ResourceState):
    """State of a GCE Static IP"""

    region = attr_property("gce.region", None)
    addr_name = attr_property("gce.name", None)
    ipAddress = attr_property("gce.ipAddress", None)

    project = attr_property("gce.project", None)
    service_account = attr_property("gce.serviceAccount", None)
    access_key_path = attr_property("gce.accessKey", None)

    @classmethod
    def get_type(cls):
        return "gce-static-ip"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(GCEStaticIPState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s


    @property
    def resource_id(self):
        return self.addr_name


    def connect(self):
        if self._conn: return self._conn

        service_account = self.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘resources.gceStaticIPs.$NAME.serviceAccount’ or $GCE_SERVICE_ACCOUNT")

        access_key_path = self.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘resources.gceStaticIPs.$NAME.accessKey’ or $ACCESS_KEY_PATH")

        project = self.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘resources.gceStaticIPs.$NAME.project’ or $GCE_PROJECT")

        self._conn = get_driver(Provider.GCE)(service_account, access_key_path, project = project)
        return self._conn

    def address(self):
        return self.connect().ex_get_address(self.addr_name, region=self.region)

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if self.project != defn.project:
                self.warn("cannot change the project of a deployed GCE static IP")

            if self.region != defn.region:
                self.warn("cannot change the region of a deployed GCE static IP")

            if defn.ipAddress and self.ipAddress != defn.ipAddress:
                self.warn("cannot change address of a deployed GCE static IP")

        self.project = defn.project
        self.service_account = defn.service_account
        self.access_key_path = defn.access_key_path
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
