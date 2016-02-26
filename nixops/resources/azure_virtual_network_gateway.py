# -*- coding: utf-8 -*-

# Automatic provisioning of Azure virtual network gateways.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import *

class AzureVirtualNetworkGatewayDefinition(ResourceDefinition):
    """Definition of an Azure Virtual Network Gateway"""

    @classmethod
    def get_type(cls):
        return "azure-virtual-network-gateway"

    @classmethod
    def get_resource_type(cls):
        return "azureVirtualNetworkGateways"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.gateway_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)
        self.copy_tags(xml)
        self.copy_option(xml, 'gatewaySize', str, empty = False)
        self.copy_option(xml, 'gatewayType', str, empty = False)
        self.copy_option(xml, 'bgpEnabled', bool)
        subnet_xml  = xml.find("attrs/attr[@name='subnet']")
        self.subnet = ResId(self.get_option_value(subnet_xml, 'network', 'res-id'),
                            subresource = self.get_option_value(subnet_xml, 'name', str),
                            subtype = 'subnets').id

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureVirtualNetworkGatewayState(ResourceState):
    """State of an Azure Virtual Network Gateway"""

    gateway_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    gateway_size = attr_property("azure.gatewaySize", None)
    gateway_type = attr_property("azure.gatewayType", None)
    bgp_enabled = attr_property("azure.bgpEnabled", None, bool)
    subnet = attr_property("azure.subnet", None)
    ip_address = attr_property("azure.ipAddress", None)
    public_ipv4 = attr_property("azure.publicIpv4", None)
    tags = attr_property("azure.tags", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-virtual-network-gateway"

    def show_type(self):
        s = super(AzureVirtualNetworkGatewayState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.gateway_name

    @property
    def full_name(self):
        return "Azure virtual network gateway '{0}'".format(self.resource_id)

    def get_resource(self):
        response = self.nrpc().send_request(self.mk_request('GET'))
        if response.status_code == 200:
            return json.loads(response.content.decode())
        else:
            return None

    def destroy_resource(self):
        self.nrpc().virtual_network_gateways.delete(self.resource_group, self.resource_id)

    defn_properties = [ 'location', 'tags', 'gateway_size',
                        'gateway_type', 'bgp_enabled', 'subnet' ]

    @property
    def ip_addr_name(self):
        return "{0}-ip-addr".format(self.gateway_name)

    def fetch_public_ip(self):
        return self.ip_address and self.nrpc().public_ip_addresses.get(
                   self.resource_group, self.ip_address).public_ip_address.ip_address


    def get_resource_url(self):
        return ("https://management.azure.com/subscriptions/{0}"
               "/resourceGroups/{1}/providers/Microsoft.Network"
               "/virtualNetworkGateways/{2}?api-version=2015-05-01-preview"
               .format(quote(self.subscription_id),
                       quote(self.resource_group),
                       quote(self.gateway_name)))

    def mk_request(self, method):
        http_request = Request()
        http_request.url = self.get_resource_url()
        http_request.method = method
        http_request.headers['Content-Type'] = 'application/json'
        return http_request

    def is_settled(self, resource):
        return resource is None or (resource.get('properties', {})
                                            .get('provisioningState', None) in ['Succeeded', 'Failed'])

    def is_failed(self, resource):
        return resource.get('properties', {}).get('provisioningState', None) == 'Failed'

    def is_deployed(self):
        return (self.ip_address is not None) or (self.state == self.UP)

    def _create_or_update(self, defn):
        ip_id = self.nrpc().public_ip_addresses.get(
                            self.resource_group,
                            self.ip_address).public_ip_address.id
        info = {
          'location': defn.location,
          'tags': defn.tags,
          'properties':{
              'gatewayType': 'Vpn',
              'vpnType': defn.gateway_type,
              'gatewaySize': defn.gateway_size,
              'bgpEnabled': defn.bgp_enabled,
              'ipConfigurations': [ {
                  'name': "default",
                  'properties': {
                      'privateIPAllocationMethod': 'Dynamic',
                      'subnet': {'id': defn.subnet},
                      'publicIPAddress': {'id': ip_id},
                  },
              } ],
          },
        };
        http_request = self.mk_request('PUT')
        http_request.data = json.dumps(info)
        http_request.headers['Content-Length'] = len(http_request.data)
        response = self.nrpc().send_request(http_request)

        if response.status_code not in [200, 201]:
            raise AzureHttpError(response.content, response.status_code)

        self.state = self.UP
        self.copy_properties(defn)
        self.log("waiting for resource to settle; certain operations might take 15-60 minutes")
        self.get_settled_resource(initial=10, max_tries=360)
        self.public_ipv4 = self.fetch_public_ip()


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')
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
                                             normalize_location(gateway['location']),
                                             can_fix = False)
                self.handle_changed_property('tags', gateway['tags'])
                properties = gateway['properties']
                # azure provides sku specification which doesn't directly map to gatewaySize
                # so we can't check gateway size
                #self.handle_changed_property('gateway_size', properties['gateway_size'])
                self.handle_changed_property('gateway_type', properties['vpnType'])
                self.handle_changed_property('bgp_enabled', properties['enableBgp'])
                ip_config = properties.get('ipConfigurations', [{}])[0].get('properties', {})
                self.handle_changed_property('subnet', ip_config['subnet']['id'])
                self.warn_if_changed(self.ip_address,
                                     ResId(ip_config.get('publicIPAddress', {}).get('id', None))['resource'],
                                     'public IP address resource', can_fix = False)
                try:
                    ip = self.fetch_public_ip()
                except azure.common.AzureMissingResourceHttpError:
                    ip = None
                    self.ip_address = None
                    self.warn('public IP address resource has been deleted behind our back')
                self.handle_changed_property('public_ipv4', ip)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.ip_address is None:
            self.log("getting an IP address")
            self.nrpc().public_ip_addresses.create_or_update(
                self.resource_group, self.ip_addr_name,
                PublicIpAddress(
                    location = defn.location,
                    public_ip_allocation_method = 'Dynamic',
                    idle_timeout_in_minutes = 4,
                ))
            self.ip_address = self.ip_addr_name

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a virtual network gateway that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0}...".format(self.full_name))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)

    def destroy(self, wipe=False):
        if self.state == self.UP:
            resource = self.get_settled_resource()
            if resource:
                if not self.confirm_destroy(abort = False):
                    return False
            else:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))

        if self.ip_address:
            self.log("releasing the ip address...")
            try:
                self.nrpc().public_ip_addresses.get(self.resource_group, self.ip_address)
                self.nrpc().public_ip_addresses.delete(self.resource_group, self.ip_address)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("seems to have been released already")
            self.public_ipv4 = None
            self.ip_address = None

        return True

    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_virtual_network import AzureVirtualNetworkState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureVirtualNetworkState) }
