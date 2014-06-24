# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Persistent Disks.

import os
import libcloud.common.google
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string, optional_int

class GCEDiskDefinition(ResourceDefinition):
    """Definition of a GCE Persistent Disk"""

    @classmethod
    def get_type(cls):
        return "gce-disk"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.disk_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")

        self.size = optional_int(xml.find("attrs/attr[@name='size']/int"))
        self.snapshot = optional_string(xml.find("attrs/attr[@name='snapshot']/string"))
        self.image = optional_string(xml.find("attrs/attr[@name='image']/string"))

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCEDiskState(ResourceState):
    """State of a GCE Persistent Disk"""

    region = attr_property("gce.region", None)
    size = attr_property("gce.size", None, int)
    disk_name = attr_property("gce.disk_name", None)

    @classmethod
    def get_type(cls):
        return "gce-disk"


    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GCEDiskState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s


    @property
    def resource_id(self):
        return self.disk_name

    def nix_name(self):
        return "gceDisks"

    def disk(self):
        return self.connect().ex_get_volume(self.disk_name, self.region)

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if self.project != defn.project:
                raise Exception("Cannot change the project of a deployed GCE disk {0}".format(defn.disk_name))

            if self.region != defn.region:
                raise Exception("Cannot change the region of a deployed GCE disk {0}".format(defn.disk_name))

            if defn.size and self.size != defn.size:
                raise Exception("Cannot change the size of a deployed GCE disk {0}".format(defn.disk_name))

        self.copy_credentials(defn)

        if check:
            try:
                disk = self.connect().ex_get_volume(defn.disk_name, defn.region)
                if self.state == self.UP:
                    if disk.size != str(self.size):
                        self.warn("GCE disk ‘{0}’ size has changed to {1}. Expected the size to be {2}".
                                  format(defn.disk_name, disk.size, self.size))
                else:
                    self.warn("GCE disk ‘{0}’ exists, but isn't supposed to. Probably, this is  the result "
                              "of a botched creation attempt and can be fixed by deletion. However, this also "
                              "could be a resource name collision, and valuable data could be lost. "
                              "Before proceeding, please ensure that the disk doesn't contain useful data."
                              .format(defn.disk_name))
                    if self.depl.logger.confirm("Are you sure you want to destroy the existing disk ‘{0}’?".format(defn.disk_name)):
                        self.log_start("destroying...")
                        disk.destroy()
                        self.log_end("done.")
                    else: raise Exception("Can't proceed further.")
            except libcloud.common.google.ResourceNotFoundError:
                if self.state == self.UP:
                    self.warn("GCE disk ‘{0}’ is supposed to exist, but is missing. Will recreate.".format(defn.disk_name))
                    self.state = self.MISSING

        if self.state != self.UP:
            if defn.snapshot:
                self.log_start("creating GCE disk of {0} GiB from snapshot ‘{1}’...".format(defn.size if defn.size else "auto", defn.snapshot))
            elif defn.image:
                self.log_start("creating GCE disk of {0} GiB from image ‘{1}’...".format(defn.size if defn.size else "auto", defn.image))
            else:
                self.log_start("creating GCE disk of {0} GiB...".format(defn.size))
            try:
                volume = self.connect().create_volume(defn.size, defn.disk_name, defn.region,
                                                      snapshot = defn.snapshot, image = defn.image,
                                                      use_existing= False)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a disk that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end("done.")
            self.state = self.UP
            self.region = defn.region
            self.size = volume.size
            self.disk_name = defn.disk_name


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                disk = self.disk()
                if not self.depl.logger.confirm("are you sure you want to destroy GCE disk ‘{0}’?".format(self.disk_name)):
                    return False
                self.log("destroying GCE disk ‘{0}’...".format(self.disk_name))
                disk.destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy GCE disk ‘{0}’ which didn't exist".format(self.disk_name))
        return True
