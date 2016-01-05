# -*- coding: utf-8 -*-

# Automatic provisioning of Azure Tables.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import StorageResourceDefinition, StorageResourceState

class AzureTableDefinition(StorageResourceDefinition):
    """Definition of an Azure Table"""

    @classmethod
    def get_type(cls):
        return "azure-table"

    @classmethod
    def get_resource_type(cls):
        return "azureTables"

    def __init__(self, xml):
        StorageResourceDefinition.__init__(self, xml)

        self.table_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'storage', 'resource')

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureTableState(StorageResourceState):
    """State of an Azure Table"""

    table_name = attr_property("azure.name", None)
    storage = attr_property("azure.storage", None)

    @classmethod
    def get_type(cls):
        return "azure-table"

    def show_type(self):
        s = super(AzureTableState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.table_name

    nix_name = "azureTables"

    @property
    def full_name(self):
        return "Azure table '{0}'".format(self.resource_id)

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
        return self.ts().get_table_acl(self.resource_id)

    def destroy_resource(self):
        self.ts().delete_table(self.resource_id, fail_not_exist = True)

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'storage')

        self.table_name = defn.table_name
        self.access_key = defn.access_key
        self.storage = defn.storage

        if check:
            table = self.get_settled_resource()
            if table is None:
                self.warn_missing_resource()
            elif self.state == self.UP:
                # FIXME: ACL handling
                self.is_settled(table) # a placeholder
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource() is not None:
                raise Exception("tried creating a table that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.storage))
            self.ts().create_table(defn.table_name, fail_on_exist = True)
            self.state = self.UP


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_storage import AzureStorageState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureStorageState)}
