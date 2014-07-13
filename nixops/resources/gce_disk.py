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

        self.disk_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'region', str)
        self.copy_option(xml, 'size', int, optional = True)
        self.copy_option(xml, 'snapshot', str, optional = True)
        self.copy_option(xml, 'image', str, optional = True)


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

    nix_name = "gceDisks"

    @property
    def full_name(self):
        return "GCE Disk '{0}'".format(self.disk_name)

    def disk(self):
        return self.connect().ex_get_volume(self.disk_name, self.region)

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(defn.size and self.size != defn.size, 'size')
        self.no_project_change(defn)
        self.no_region_change(defn)

        self.copy_credentials(defn)
        self.disk_name = defn.disk_name

        if check:
            try:
                disk = self.disk()
                if self.state == self.UP:
                    self.handle_changed_property('region', disk.extra['zone'].name, can_fix = False)
                    self.handle_changed_property('size', int(disk.size), can_fix = False)
                else:
                    self.warn_not_supposed_to_exist(valuable_data = True)
                    self.confirm_destroy(disk, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            extra_msg = ( " from snapshot '{0}'".format(defn.snapshot) if defn.snapshot
                     else " from image '{0}'".format(defn.image)       if defn.image
                     else "" )
            self.log_start("Creating GCE Disk of {0} GiB{1}..."
                           .format(defn.size if defn.size else "auto", extra_msg))
            try:
                volume = self.connect().create_volume(defn.size, defn.disk_name, defn.region,
                                                      snapshot = defn.snapshot, image = defn.image,
                                                      use_existing= False)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a disk that already exists. "
                                "Please run 'deploy --check' to fix this.")

            self.log_end("done.")
            self.state = self.UP
            self.region = defn.region
            self.size = volume.size


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                return self.confirm_destroy(self.disk(), self.full_name, abort = False)
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy {0} which didn't exist".format(self.full_name))
        return True
