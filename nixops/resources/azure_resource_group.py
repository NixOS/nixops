# -*- coding: utf-8 -*-

# Automatic provisioning of Azure resource groups.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, normalize_location
from azure.mgmt.resource import ResourceGroup

class AzureResourceGroupDefinition(ResourceDefinition):
    """Definition of an Azure Resource Group"""

    @classmethod
    def get_type(cls):
        return "azure-resource-group"

    @classmethod
    def get_resource_type(cls):
        return "azureResourceGroups"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.resource_group_name = self.get_option_value(xml, 'name', str)
        self.copy_location(xml)
        self.copy_tags(xml)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureResourceGroupState(ResourceState):
    """State of an Azure Resource Group"""

    resource_group_name = attr_property("azure.name", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-resource-group"

    def show_type(self):
        s = super(AzureResourceGroupState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.resource_group_name

    @property
    def full_name(self):
        return "Azure resource group '{0}'".format(self.resource_group_name)

    def get_resource(self):
        try:
            return self.rmc().resource_groups.get(self.resource_group_name).resource_group
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.rmc().resource_groups.delete(self.resource_group_name)

    defn_properties = [ 'tags', 'location' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')

        self.copy_mgmt_credentials(defn)
        self.resource_group_name = defn.resource_group_name

        if check:
            rg = self.get_settled_resource()
            if not rg:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location', normalize_location(rg.location),
                                             can_fix = False)
                self.handle_changed_property('tags', rg.tags)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a resource group that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self.rmc().resource_groups.create_or_update(
                defn.resource_group_name,
                ResourceGroup(location = defn.location,
                              tags = defn.tags))
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self.rmc().resource_groups.create_or_update(
                defn.resource_group_name,
                ResourceGroup(location = defn.location,
                              tags = defn.tags))
            self.copy_properties(defn)
