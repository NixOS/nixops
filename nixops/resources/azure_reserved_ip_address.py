# -*- coding: utf-8 -*-

# Automatic provisioning of Azure reserved IP addresses.

import os
import azure
import time

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState

from azure.mgmt.network import *

class AzureReservedIPAddressDefinition(ResourceDefinition):
    """Definition of an Azure Reserved IP Address"""

    @classmethod
    def get_type(cls):
        return "azure-reserved-ip-address"

    @classmethod
    def get_resource_type(cls):
        return "azureReservedIPAddresses"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.reserved_ip_address_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_option(xml, 'location', str)
        self.copy_tags(xml)
        self.copy_option(xml, 'idleTimeout', int)
        self.copy_option(xml, 'domainNameLabel', str, optional = True)
        self.copy_option(xml, 'reverseFqdn', str, optional = True)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureReservedIPAddressState(ResourceState):
    """State of an Azure Reserved IP Address"""

    reserved_ip_address_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')
    idle_timeout = attr_property("azure.idleTimeout", None, int)
    domain_name_label = attr_property("azure.domainNameLabel", None)
    reverse_fqdn = attr_property("azure.reverseFqdn", None)

    ip_address = attr_property("azure.ipAddress", None)

    @classmethod
    def get_type(cls):
        return "azure-reserved-ip-address"

    def show_type(self):
        s = super(AzureReservedIPAddressState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.reserved_ip_address_name

    nix_name = "azureReservedIPAddresses"

    @property
    def full_name(self):
        return "Azure reserved IP address '{0}'".format(self.reserved_ip_address_name)

    @property
    def public_ipv4(self):
        return self.ip_address

    def get_resource(self):
        try:
            return self.nrpc().public_ip_addresses.get(
                      self.resource_group, self.resource_id).public_ip_address
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.nrpc().public_ip_addresses.delete(self.resource_group, self.resource_id)

    def is_settled(self, resource):
        return resource is None or (resource.provisioning_state == 'Succeeded')

    defn_properties = [ 'location', 'tags', 'idle_timeout', 'domain_name_label', 'reverse_fqdn' ]

    def _update_resource(self, defn):
        dns_settings = PublicIpAddressDnsSettings(
                                domain_name_label = defn.domain_name_label,
                                reverse_fqdn = defn.reverse_fqdn
                       ) if defn.domain_name_label or defn.reverse_fqdn else None
        self.nrpc().public_ip_addresses.create_or_update(
                        defn.resource_group, defn.reserved_ip_address_name,
                        PublicIpAddress(
                            location = defn.location,
                            public_ip_allocation_method = 'Static',
                            idle_timeout_in_minutes = defn.idle_timeout,
                            tags = defn.tags,
                            dns_settings = dns_settings
                        ))
        self.state = self.UP
        self.copy_properties(defn)
        self.ip_address = self.get_settled_resource().ip_address


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.reserved_ip_address_name = defn.reserved_ip_address_name
        self.resource_group = defn.resource_group

        if check:
            address = self.get_settled_resource()
            if not address:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location', address.location, can_fix = False)
                self.handle_changed_property('tags', address.tags)
                self.handle_changed_property('ip_address', address.ip_address, property_name = '')
                self.handle_changed_property('idle_timeout', address.idle_timeout_in_minutes)
                _dns = address.dns_settings
                self.handle_changed_property('domain_name_label',
                                              _dns and _dns.domain_name_label)
                self.handle_changed_property('reverse_fqdn',
                                              _dns and _dns.reverse_fqdn)
            else:
                self.warn_not_supposed_to_exist(valuable_resource = True)
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a reserved IP address that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self._update_resource(defn)
            self.log("reserved IP address: {0}".format(self.ip_address))

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._update_resource(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState)}