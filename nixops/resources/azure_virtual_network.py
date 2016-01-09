# -*- coding: utf-8 -*-

# Automatic provisioning of Azure virtual networks.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState

from azure.mgmt.network import VirtualNetwork, AddressSpace, Subnet

class AzureVirtualNetworkDefinition(ResourceDefinition):
    """Definition of an Azure Virtual Network"""

    @classmethod
    def get_type(cls):
        return "azure-virtual-network"

    @classmethod
    def get_resource_type(cls):
        return "azureVirtualNetworks"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.network_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'addressSpace', 'strlist')
        if len(self.address_space) == 0:
            raise Exception("virtual network {0}: must specify at least one address space"
                            .format(self.network_name))
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_option(xml, 'location', str, empty = False)

        self.copy_tags(xml)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureVirtualNetworkState(ResourceState):
    """State of an Azure Virtual Network"""

    network_name = attr_property("azure.name", None)
    address_space = attr_property("azure.addressSpace", [], 'json')
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-virtual-network"

    def show_type(self):
        s = super(AzureVirtualNetworkState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.network_name

    nix_name = "azureVirtualNetworks"

    @property
    def full_name(self):
        return "Azure virtual network '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.nrpc().virtual_networks.get(self.resource_group, self.resource_id).virtual_network
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.nrpc().virtual_networks.delete(self.resource_group, self.resource_id)

    def is_settled(self, resource):
        return resource is None or (resource.provisioning_state == 'Succeeded')

    defn_properties = [ 'location', 'tags', 'address_space' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.network_name = defn.network_name
        self.resource_group = defn.resource_group

        if check:
            network = self.get_settled_resource()
            if not network:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location', network.location, can_fix = False)
                self.handle_changed_property('tags', network.tags)
                self.handle_changed_property('address_space', network.address_space.address_prefixes)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a virtual network that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self.nrpc().virtual_networks.create_or_update(defn.resource_group, defn.network_name,
                                                          VirtualNetwork(
                                                              location = defn.location,
                                                              address_space = AddressSpace(
                                                                  address_prefixes = defn.address_space),
                                                              tags = defn.tags))
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self.nrpc().virtual_networks.create_or_update(defn.resource_group, defn.network_name,
                                                          VirtualNetwork(
                                                              location = defn.location,
                                                              address_space = AddressSpace(
                                                                  address_prefixes = defn.address_space),
                                                              tags = defn.tags))
            self.copy_properties(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState)}
