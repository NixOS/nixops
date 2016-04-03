# -*- coding: utf-8 -*-

# Automatic provisioning of Azure local network gateways.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import *

class AzureLocalNetworkGatewayDefinition(ResourceDefinition):
    """Definition of an Azure Local Network Gateway"""

    @classmethod
    def get_type(cls):
        return "azure-local-network-gateway"

    @classmethod
    def get_resource_type(cls):
        return "azureLocalNetworkGateways"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.gateway_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)
        self.copy_option(xml, 'ipAddress', str, empty = False)
        self.copy_option(xml, 'addressSpace', 'strlist')
        if len(self.address_space) == 0:
            raise Exception("local network gateway {0}: must specify at least one address space"
                            .format(self.gateway_name))
        self.copy_tags(xml)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureLocalNetworkGatewayState(ResourceState):
    """State of an Azure Local Network Gateway"""

    gateway_name = attr_property("azure.name", None)
    address_space = attr_property("azure.addressSpace", [], 'json')
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    ip_address = attr_property("azure.ipAddress", None)
    tags = attr_property("azure.tags", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-local-network-gateway"

    def show_type(self):
        s = super(AzureLocalNetworkGatewayState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.gateway_name

    @property
    def full_name(self):
        return "Azure local network gateway '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.nrpc().local_network_gateways.get(self.resource_group,
                                                          self.resource_id).local_network_gateway
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.nrpc().local_network_gateways.delete(self.resource_group, self.resource_id)

    defn_properties = [ 'location', 'tags', 'address_space', 'ip_address' ]

    def _create_or_update(self, defn):
        self.nrpc().local_network_gateways.create_or_update(
            defn.resource_group, defn.gateway_name,
            LocalNetworkGateway(
                location = defn.location,
                gateway_ip_address = defn.ip_address,
                local_network_site_address_space = AddressSpace(
                    address_prefixes = defn.address_space),
                tags = defn.tags))
        self.state = self.UP
        self.copy_properties(defn)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_location_change(defn)
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.gateway_name = defn.gateway_name
        self.resource_group = defn.resource_group

        if check:
            gateway = self.get_settled_resource()
            if not gateway:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(gateway)
                self.handle_changed_property('location',
                                             normalize_location(gateway.location), can_fix = False)
                self.handle_changed_property('tags', gateway.tags)
                self.handle_changed_property('address_space',
                                             gateway.local_network_site_address_space and
                                             gateway.local_network_site_address_space.address_prefixes)
                self.handle_changed_property('ip_address',
                                             gateway.gateway_ip_address)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a local network gateway that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0}...".format(self.full_name))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState)}
