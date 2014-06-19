# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Persistent Disks.

import os
import libcloud.common.google
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver

from nixops.util import attr_property
import nixops.resources


class GCEDiskDefinition(nixops.resources.ResourceDefinition):
    """Definition of a GCE Persistent Disk"""

    @classmethod
    def get_type(cls):
        return "gce-disk"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)

        self.disk_name = xml.find("attrs/attr[@name='name']/string").get("value")
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")

        # FIXME: factor this out
        self.project = xml.find("attrs/attr[@name='project']/string").get("value")
        self.service_account = xml.find("attrs/attr[@name='serviceAccount']/string").get("value")
        self.access_key_path = xml.find("attrs/attr[@name='accessKey']/string").get("value")

        sz = xml.find("attrs/attr[@name='size']/int")
        self.size = ( int(sz.get("value")) if sz is not None else None )

        ss = xml.find("attrs/attr[@name='snapshot']/string")
        self.snapshot = ( ss.get("value") if ss is not None else None )

        img = xml.find("attrs/attr[@name='image']/string")
        self.image = ( img.get("value") if img is not None else None )

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GCEDiskState(nixops.resources.ResourceState):
    """State of a GCE Persistent Disk"""

    region = attr_property("gce.region", None)
    size = attr_property("gce.size", None, int)
    disk_name = attr_property("gce.disk_name", None)

    project = attr_property("gce.project", None)
    service_account = attr_property("gce.serviceAccount", None)
    access_key_path = attr_property("gce.accessKey", None)

    @classmethod
    def get_type(cls):
        return "gce-disk"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


    def show_type(self):
        s = super(GCEDiskState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s


    @property
    def resource_id(self):
        return self.disk_name


    def connect(self):
        if self._conn: return self._conn

        service_account = self.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘resources.gceDisks.$NAME.serviceAccount’ or $GCE_SERVICE_ACCOUNT")

        access_key_path = self.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘resources.gceDisks.$NAME.accessKey’ or $ACCESS_KEY_PATH")

        project = self.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘resources.gceDisks.$NAME.project’ or $GCE_PROJECT")

        self._conn = get_driver(Provider.GCE)(service_account, access_key_path, project = project)
        return self._conn

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

        self.service_account = defn.service_account
        self.access_key_path = defn.access_key_path
        self.project = defn.project

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
            with self.depl._db:
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
