# -*- coding: utf-8 -*-

# Automatic provisioning of Azure disks.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState
from azure.servicemanagement import _XmlSerializer, _lower

def normalize_empty(x):
    return (x if x != "" else None)


class AzureDiskDefinition(ResourceDefinition):
    """Definition of an Azure Disk"""

    @classmethod
    def get_type(cls):
        return "azure-disk"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.disk_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'label', str, empty = False)
        self.copy_option(xml, 'mediaLink', str, empty = False)
        self.copy_option(xml, 'os', str, optional = True)
        if self.os not in [None, "Linux", "Windows"]:
            raise Exception("Disk {0} OS must be null, Linux or Windows"
                            .format(self.disk_name))

    def show_type(self):
        return self.get_type()


class AzureDiskState(ResourceState):
    """State of an Azure Disk"""

    disk_name = attr_property("azure.name", None)
    label = attr_property("azure.label", None)
    os = attr_property("azure.os", None)
    size = attr_property("azure.size", None, int)
    media_link = attr_property("azure.mediaLink", None)

    @classmethod
    def get_type(cls):
        return "azure-disk"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        return super(AzureDiskState, self).show_type()

    @property
    def resource_id(self):
        return self.disk_name

    nix_name = "azureDisks"

    @property
    def full_name(self):
        return "Azure disk '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.sms().get_disk(self.resource_id)
        except azure.WindowsAzureMissingResourceError:
            return None

    def destroy_resource(self):
        self.sms().delete_disk(self.resource_id)

    def is_settled(self, resource):
        return True


   # an ugly workaround for a bug:
   # http://www.biztalkgurus.com/biztalk_server/biztalk_blogs/b/biztalk/archive/2012/10/05/working-with-the-add-disk-operation-of-the-windows-azure-rest-api.aspx
    def _create_disk(self, has_operating_system, label, media_link, name, os):
        if has_operating_system:
            return self.sms()._perform_post(
                      self.sms()._get_disk_path(),
                      _XmlSerializer.doc_from_data(
                          'Disk',
                          [('OS', os),
                          ('HasOperatingSystem', has_operating_system, _lower),
                          ('Label', label),
                          ('MediaLink', media_link),
                          ('Name', name)]))
        else:
            return self.sms().add_disk(has_operating_system, label, media_link, name, os)

    def _update_disk(self, has_operating_system, label, media_link, name, os):
        return self.sms().update_disk(name, has_operating_system, label, media_link, name, os)


    defn_properties = [ 'label', 'media_link', 'os' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'media_link')
        self.no_property_change(defn, 'os')

        self.copy_credentials(defn)
        self.disk_name = defn.disk_name

        if check:
            disk = self.get_settled_resource()
            if not disk:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('media_link', disk.media_link, can_fix = False)
                self.handle_changed_property('label', disk.label)
                self.handle_changed_property('os', normalize_empty(disk.os), can_fix = False)
                self.handle_changed_property('size', disk.logical_disk_size_in_gb)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a disk that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} using {1}...".format(self.full_name, defn.media_link))
            self._create_disk(defn.os is not None, defn.label, defn.media_link,
                              defn.disk_name, defn.os or "")
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self._update_disk(defn.os is not None, defn.label,
                              defn.media_link, defn.disk_name, defn.os or "")
            self.copy_properties(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_blob import AzureBLOBState
        from nixops.resources.azure_blob_container import AzureBLOBContainerState
        from nixops.resources.azure_storage import AzureStorageState
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState) or
                     isinstance(r, AzureBLOBState)}
