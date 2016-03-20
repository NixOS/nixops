# -*- coding: utf-8 -*-

# Automatic provisioning of Azure availability sets.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, normalize_location

from azure.mgmt.compute import AvailabilitySet

class AzureVirtualNetworkDefinition(ResourceDefinition):
    """Definition of an Azure Availability Set"""

    @classmethod
    def get_type(cls):
        return "azure-availability-set"

    @classmethod
    def get_resource_type(cls):
        return "azureAvailabilitySets"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.availability_set_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)
        self.copy_tags(xml)
        self.copy_option(xml, 'platformUpdateDomainCount', int)
        self.copy_option(xml, 'platformFaultDomainCount', int)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureAvailabilitySetState(ResourceState):
    """State of an Azure Availability Set"""

    availability_set_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')
    platform_update_domain_count = attr_property("azure.platformUpdateDomainCount", None, int)
    platform_fault_domain_count = attr_property("azure.platformFaultDomainCount", None, int)

    @classmethod
    def get_type(cls):
        return "azure-availability-set"

    def show_type(self):
        s = super(AzureAvailabilitySetState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.availability_set_name

    @property
    def full_name(self):
        return "Azure availability set '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.cmc().availability_sets.get(
                       self.resource_group, self.resource_id).availability_set
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.cmc().availability_sets.delete(self.resource_group, self.resource_id)

    def is_settled(self, resource):
        return True

    defn_properties = [ 'location', 'tags', 'platform_update_domain_count',
                        'platform_fault_domain_count' ]

    def _create_or_update(self, defn):
        self.cmc().availability_sets.create_or_update(
            defn.resource_group,
            AvailabilitySet(
                name = defn.availability_set_name,
                location = defn.location,
                tags = defn.tags,
                platform_update_domain_count = defn.platform_update_domain_count,
                platform_fault_domain_count = defn.platform_fault_domain_count,
        ))
        self.state = self.UP
        self.copy_properties(defn)

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')
        self.no_property_change(defn, 'platform_update_domain_count')
        self.no_property_change(defn, 'platform_fault_domain_count')

        self.copy_mgmt_credentials(defn)
        self.availability_set_name = defn.availability_set_name
        self.resource_group = defn.resource_group

        if check:
            aset = self.get_settled_resource()
            if not aset:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location', normalize_location(aset.location),
                                             can_fix = False)
                self.handle_changed_property('tags', aset.tags)
                self.handle_changed_property('platform_update_domain_count',
                                             aset.platform_update_domain_count,
                                             can_fix = False)
                self.handle_changed_property('platform_fault_domain_count',
                                             aset.platform_fault_domain_count,
                                             can_fix = False)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating an availability set that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState)}
