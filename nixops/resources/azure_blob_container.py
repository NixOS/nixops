# -*- coding: utf-8 -*-

# Automatic provisioning of Azure BLOB Containers.

import os
import azure
from azure.storage import BlobService

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState

class AzureBLOBContainerDefinition(ResourceDefinition):
    """Definition of an Azure BLOB Container"""

    @classmethod
    def get_type(cls):
        return "azure-blob-container"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.container_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'accessKey', str, optional = True)
        self.copy_option(xml, 'acl', str, optional = True)
        self.copy_option(xml, 'storage', 'resource')
        self.metadata = {
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='metadata']/attrs/attr")
        }

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureBLOBContainerState(ResourceState):
    """State of an Azure BLOB Container"""

    container_name = attr_property("azure.name", None)
    access_key = attr_property("azure.accessKey", None)
    acl = attr_property("azure.acl", None)
    storage = attr_property("azure.storage", None)
    metadata = attr_property("azure.metadata", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-blob-container"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)
        self._bs = None

    def show_type(self):
        s = super(AzureBLOBContainerState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.container_name

    nix_name = "azureBlobContainers"

    @property
    def full_name(self):
        return "Azure BLOB container '{0}'".format(self.resource_id)

    def get_key(self):
        storage = next((r for r in self.depl.resources.values()
                          if getattr(r, 'storage_name', None) == self.storage), None)
        access_key = self.access_key or (storage and storage.access_key)

        if not access_key:
            raise Exception("Can't obtain the access key needed to create {0}"
                            .format(self.full_name))
        return access_key

    def bs(self):
        if not self._bs:
            self._bs = BlobService(self.storage, self.get_key())
        return self._bs

    def is_settled(self, resource):
        return True

    def get_resource(self):
        try:
            return self.bs().get_container_properties(self.resource_id)
        except azure.WindowsAzureMissingResourceError:
            return None

    def destroy_resource(self):
        self.bs().delete_container(self.resource_id, fail_not_exist = True)

    defn_properties = [ 'acl', 'metadata' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'storage')

        self.copy_credentials(defn)
        self.container_name = defn.container_name
        self.access_key = defn.access_key
        self.storage = defn.storage

        if check:
            container = self.get_settled_resource()
            if not container:
                self.warn_missing_resource()
            elif self.state == self.UP:
                # acl = bs.
                #self.handle_changed_property('acl', container.acl)
                metadata = { k[10:] : v
                             for k, v in container.items()
                             if k.startswith('x-ms-meta-') }
                self.handle_changed_property('metadata', metadata)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a container that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.storage))
            self.bs().create_container(defn.container_name,
                                       x_ms_meta_name_values = defn.metadata,
                                       x_ms_blob_public_access = defn.acl,
                                       fail_on_exist = True)
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self.bs().set_container_metadata(self.container_name, x_ms_meta_name_values = defn.metadata)
            self.metadata = defn.metadata
            self.bs().set_container_acl(self.container_name, x_ms_blob_public_access = defn.acl)
            self.acl = defn.acl


    def create_after(self, resources, defn):
        from nixops.resources.azure_affinity_group import AzureAffinityGroupState
        return {r for r in resources
                  if isinstance(r, AzureAffinityGroupState)}
