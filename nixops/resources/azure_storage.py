# -*- coding: utf-8 -*-

# Automatic provisioning of Azure storages.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState

from azure.mgmt.storage import StorageAccountCreateParameters, StorageAccountUpdateParameters, CustomDomain

class AzureStorageDefinition(ResourceDefinition):
    """Definition of an Azure Storage"""

    @classmethod
    def get_type(cls):
        return "azure-storage"

    @classmethod
    def get_resource_type(cls):
        return "azureStorages"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.storage_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_option(xml, 'accountType', str, empty = False)
        self.copy_option(xml, 'activeKey', str, empty = False)
        if self.active_key not in ['primary', 'secondary']:
            raise Exception("Allowed activeKey values are: 'primary' and 'secondary'")
        self.copy_option(xml, 'location', str, empty = False)
        self.copy_option(xml, 'customDomain', str)
        self.copy_tags(xml)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureStorageState(ResourceState):
    """State of an Azure Storage"""

    storage_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    account_type = attr_property("azure.accountType", None)
    custom_domain = attr_property("azure.customDomain", None)
    tags = attr_property("azure.tags", {}, 'json')

    active_key = attr_property("azure.activeKey", None)
    primary_key = attr_property("azure.primaryKey", None)
    secondary_key = attr_property("azure.secondaryKey", None)

    @classmethod
    def get_type(cls):
        return "azure-storage"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(AzureStorageState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.storage_name

    nix_name = "azureStorages"

    @property
    def full_name(self):
        return "Azure storage '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.smc().storage_accounts.get_properties(self.resource_group,self.resource_id).storage_account
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.smc().storage_accounts.delete(self.resource_group, self.resource_id)

    def is_settled(self, resource):
        return resource is None or (resource.provisioning_state == 'Succeeded')

    @property
    def access_key(self):
        return ((self.active_key == 'primary') and self.primary_key) or self.secondary_key

    defn_properties = [ 'location', 'account_type', 'tags', 'custom_domain' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.storage_name = defn.storage_name
        self.resource_group = defn.resource_group
        self.active_key = defn.active_key

        if check:
            storage = self.get_settled_resource()
            if not storage:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location', storage.location, can_fix = False)
                self.handle_changed_property('account_type', storage.account_type)
                self.handle_changed_property('tags', storage.tags)
                self.handle_changed_property('custom_domain', (storage.custom_domain and storage.custom_domain.name) or "")

                keys = self.smc().storage_accounts.list_keys(self.resource_group, self.storage_name).storage_account_keys
                self.handle_changed_property('primary_key', keys.key1)
                self.handle_changed_property('secondary_key', keys.key2)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a storage that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self.smc().storage_accounts.create(defn.resource_group, defn.storage_name,
                                               StorageAccountCreateParameters(
                                                   account_type = defn.account_type,
                                                   location = defn.location,
                                                   tags = defn.tags))
            self.state = self.UP
            self.copy_properties(defn)
            self.custom_domain = ""
            # getting keys fails until the storage is fully provisioned
            self.log("waiting for the storage to settle; this may take several minutes...")
            self.get_settled_resource()
            keys = self.smc().storage_accounts.list_keys(self.resource_group, self.storage_name).storage_account_keys
            self.primary_key = keys.key1
            self.secondary_key = keys.key2

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            # as per Azure documentation, this API can only
            # change one property per call, so we call it 3 times
            if self.tags != defn.tags:
                self.smc().storage_accounts.update(self.resource_group, self.storage_name,
                                                   StorageAccountUpdateParameters(tags = defn.tags))
                self.tags = defn.tags

            if self.account_type != defn.account_type:
                self.smc().storage_accounts.update(self.resource_group, self.storage_name,
                                                   StorageAccountUpdateParameters(
                                                       account_type = defn.account_type))
                self.account_type = defn.account_type

            if self.custom_domain != defn.custom_domain:
                self.smc().storage_accounts.update(self.resource_group, self.storage_name,
                                                   StorageAccountUpdateParameters(
                                                       custom_domain =
                                                           CustomDomain(name = defn.custom_domain)))
                self.custom_domain = defn.custom_domain


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState)}
