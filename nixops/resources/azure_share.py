# -*- coding: utf-8 -*-

# Automatic provisioning of Azure Shares.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import StorageResourceDefinition, StorageResourceState

from nixops.resources.azure_resource_group import AzureResourceGroupState
from nixops.resources.azure_storage import AzureStorageState

class AzureShareDefinition(StorageResourceDefinition):
    """Definition of an Azure Share"""

    @classmethod
    def get_type(cls):
        return "azure-share"

    @classmethod
    def get_resource_type(cls):
        return "azureShares"

    def __init__(self, xml):
        StorageResourceDefinition.__init__(self, xml)

        self.share_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'storage', 'resource')
        self.metadata = {
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='metadata']/attrs/attr")
        }

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureShareState(StorageResourceState):
    """State of an Azure Share"""

    share_name = attr_property("azure.name", None)
    storage = attr_property("azure.storage", None)
    metadata = attr_property("azure.metadata", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-share"

    def show_type(self):
        s = super(AzureShareState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.share_name

    nix_name = "azureShares"

    @property
    def full_name(self):
        return "Azure share '{0}'".format(self.resource_id)

    def get_storage_name(self):
        return self.storage

    def get_key(self):
        storage = self.get_resource_state(AzureStorageState, self.storage)
        access_key = self.access_key or (storage and storage.access_key)

        if not access_key:
            raise Exception("Can't obtain the access key needed to manage {0}"
                            .format(self.full_name))
        return access_key

    def is_settled(self, resource):
        return True

    def get_resource_allow_exceptions(self):
        return self.fs().get_share_properties(self.resource_id)

    def destroy_resource(self):
        self.fs().delete_share(self.resource_id, fail_not_exist = True)

    defn_properties = [ 'metadata' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'storage')

        self.share_name = defn.share_name
        self.access_key = defn.access_key
        self.storage = defn.storage

        if check:
            share = self.get_settled_resource()
            if not share:
                self.warn_missing_resource()
            elif self.state == self.UP:
                metadata = { k[10:] : v
                             for k, v in share.items()
                             if k.startswith('x-ms-meta-') }
                self.handle_changed_property('metadata', metadata)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a share that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.storage))
            self.fs().create_share(defn.share_name,
                                   x_ms_meta_name_values = defn.metadata,
                                   fail_on_exist = True)
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self.fs().set_share_metadata(self.share_name, x_ms_meta_name_values = defn.metadata)
            self.metadata = defn.metadata


    def create_after(self, resources, defn):
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureStorageState)}
