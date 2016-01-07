# -*- coding: utf-8 -*-

# Automatic provisioning of Azure Queues.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import StorageResourceDefinition, StorageResourceState

class AzureQueueDefinition(StorageResourceDefinition):
    """Definition of an Azure Queue"""

    @classmethod
    def get_type(cls):
        return "azure-queue"

    @classmethod
    def get_resource_type(cls):
        return "azureQueues"

    def __init__(self, xml):
        StorageResourceDefinition.__init__(self, xml)

        self.queue_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'storage', 'resource')
        self.metadata = {
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='metadata']/attrs/attr")
        }
        self.copy_signed_identifiers(xml.find("attrs/attr[@name='acl']"))

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureQueueState(StorageResourceState):
    """State of an Azure Queue"""

    queue_name = attr_property("azure.name", None)
    storage = attr_property("azure.storage", None)
    signed_identifiers = attr_property("azure.signedIdentifiers", {}, 'json')
    metadata = attr_property("azure.metadata", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-queue"

    def show_type(self):
        s = super(AzureQueueState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.queue_name

    nix_name = "azureQueues"

    @property
    def full_name(self):
        return "Azure queue '{0}'".format(self.resource_id)

    def get_storage_name(self):
        return self.storage

    def get_storage_resource(self):
        return self.storage and next(
                  (r for r in self.depl.resources.values()
                     if getattr(r, 'storage_name', None) == self.storage), None)

    def get_key(self):
        storage = self.get_storage_resource()
        access_key = self.access_key or (storage and storage.access_key)

        if not access_key:
            raise Exception("Can't obtain the access key needed to manage {0}"
                            .format(self.full_name))
        return access_key

    def is_settled(self, resource):
        return True

    def get_resource_allow_exceptions(self):
        return self.qs().get_queue_metadata(self.resource_id)

    def destroy_resource(self):
        self.qs().delete_queue(self.resource_id, fail_not_exist = True)

    defn_properties = [ 'metadata' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'storage')

        self.queue_name = defn.queue_name
        self.access_key = defn.access_key
        self.storage = defn.storage

        if check:
            queue = self.get_settled_resource()
            if not queue:
                self.warn_missing_resource()
            elif self.state == self.UP:
                metadata = { k[10:] : v
                             for k, v in queue.items()
                             if k.startswith('x-ms-meta-') }
                self.handle_changed_property('metadata', metadata)
                self.handle_changed_signed_identifiers(
                    self.qs().get_queue_acl(self.queue_name))
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a queue that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.storage))
            self.qs().create_queue(defn.queue_name,
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
            self.qs().set_queue_metadata(self.queue_name, x_ms_meta_name_values = defn.metadata)
            self.metadata = defn.metadata

        if self.signed_identifiers != defn.signed_identifiers:
            self.log("updating the ACL of {0}..."
                     .format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            signed_identifiers = self._dict_to_signed_identifiers(defn.signed_identifiers)
            self.qs().set_queue_acl(self.queue_name,
                                    signed_identifiers = signed_identifiers)
            self.signed_identifiers = defn.signed_identifiers


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_storage import AzureStorageState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureStorageState)}
