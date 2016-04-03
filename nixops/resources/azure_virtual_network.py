# -*- coding: utf-8 -*-

# Automatic provisioning of Azure virtual networks.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import VirtualNetwork, AddressSpace, Subnet, DhcpOptions

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
        self.copy_option(xml, 'dnsServers', 'strlist')
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)

        self.copy_tags(xml)

        self.subnets = {
            _s.get("name"): self._parse_subnet(_s)
            for _s in xml.findall("attrs/attr[@name='subnets']/attrs/attr")
        }

    def _parse_subnet(self, xml):
        return {
            'address_prefix': self.get_option_value(xml, 'addressPrefix', str, empty = False),
            'security_group': self.get_option_value(xml, 'securityGroup', 'res-id', optional = True),
        }

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureVirtualNetworkState(ResourceState):
    """State of an Azure Virtual Network"""

    network_name = attr_property("azure.name", None)
    address_space = attr_property("azure.addressSpace", [], 'json')
    dns_servers = attr_property("azure.dnsServers", [], 'json')
    subnets = attr_property("azure.subnets", {}, 'json')
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

    defn_properties = [ 'location', 'tags', 'address_space', 'dns_servers', 'subnets' ]

    def _create_or_update(self, defn):
        self.nrpc().virtual_networks.create_or_update(
            defn.resource_group, defn.network_name,
            VirtualNetwork(
                location = defn.location,
                address_space = AddressSpace(
                    address_prefixes = defn.address_space),
                dhcp_options = DhcpOptions(
                    dns_servers = defn.dns_servers),
                subnets = [
                    Subnet(
                        name = _name,
                        address_prefix = _s['address_prefix'],
                        network_security_group = _s['security_group'] and
                                                 ResId(_s['security_group']),
                    ) for _name, _s in defn.subnets.iteritems()
                ],
                tags = defn.tags))
        self.state = self.UP
        self.copy_properties(defn)


    def handle_changed_subnets(self, subnets):
        def update_subnets(k, v):
            x = self.subnets
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.subnets = x

        for _subnet in subnets:
            _s_name = next((_n for _n, _x in self.subnets.iteritems() if _n == _subnet.name), None)
            if _s_name is None:
                self.warn("found unexpected subnet {0}".format(_subnet.name))
                update_subnets(_subnet.name, {"dummy": True})
        for _name, _s_subnet in self.subnets.iteritems():
            if _s_subnet.get("dummy", False): continue
            subnet_res_name = "subnet {0}".format(_name)
            subnet = next((_r for _r in subnets if _r.name == _name), None)
            if subnet is None:
                self.warn("{0} has been deleted behind our back".format(subnet_res_name))
                update_subnets(_name, None)
                continue
            self.handle_changed_dict(_s_subnet, 'address_prefix',
                                     subnet.address_prefix,
                                     resource_name = subnet_res_name)
            self.handle_changed_dict(_s_subnet, 'security_group',
                                     subnet.network_security_group and
                                     subnet.network_security_group.id,
                                     resource_name = subnet_res_name)
            update_subnets(_name, _s_subnet)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_location_change(defn)
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.network_name = defn.network_name
        self.resource_group = defn.resource_group

        if check:
            network = self.get_settled_resource()
            if not network:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(network)
                self.handle_changed_property('location',
                                             normalize_location(network.location),
                                             can_fix = False)
                self.handle_changed_property('tags', network.tags)
                self.handle_changed_property('address_space',
                                             network.address_space.address_prefixes)
                self.handle_changed_subnets(network.subnets)
                self.handle_changed_property('dns_servers',
                                             network.dhcp_options and
                                             network.dhcp_options.dns_servers)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a virtual network that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_network_security_group import AzureNetworkSecurityGroupState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureNetworkSecurityGroupState) }
