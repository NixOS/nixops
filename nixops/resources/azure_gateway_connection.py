# -*- coding: utf-8 -*-

# Automatic provisioning of Azure virtual network gateway connections.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import *

class AzureGatewayConnectionDefinition(ResourceDefinition):
    """Definition of an Azure Virtual Network Gateway Connection"""

    @classmethod
    def get_type(cls):
        return "azure-gateway-connection"

    @classmethod
    def get_resource_type(cls):
        return "azureGatewayConnections"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.connection_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)
        self.copy_tags(xml)

        self.copy_option(xml, 'virtualNetworkGateway1', 'res-id', optional = True)
        self.copy_option(xml, 'virtualNetworkGateway2', 'res-id', optional = True)
        self.copy_option(xml, 'localNetworkGateway2', 'res-id', optional = True)
        self.copy_option(xml, 'connectionType', str)
        self.copy_option(xml, 'routingWeight', int)
        self.copy_option(xml, 'sharedKey', str, optional = True)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureGatewayConnectionState(ResourceState):
    """State of an Azure Virtual Network Gateway Connection"""

    connection_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')

    virtual_network_gateway1 = attr_property("azure.virtualNetworkGateway1", None)
    virtual_network_gateway2 = attr_property("azure.virtualNetworkGateway2", None)
    local_network_gateway2 = attr_property("azure.localNetworkGateway2", None)
    connection_type = attr_property("azure.connectionType", None)
    routing_weight = attr_property("azure.routingWeight", None, int)
    shared_key = attr_property("azure.sharedKey", None)

    @classmethod
    def get_type(cls):
        return "azure-gateway-connection"

    def show_type(self):
        s = super(AzureGatewayConnectionState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.connection_name

    @property
    def full_name(self):
        return "Azure virtual network gateway connection '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.nrpc().virtual_network_gateway_connections.get(
                      self.resource_group,
                      self.resource_id).virtual_network_gateway_connection
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.nrpc().virtual_network_gateway_connections.delete(self.resource_group,
                                                               self.resource_id)

    defn_properties = [ 'location', 'tags', 'virtual_network_gateway1',
                        'virtual_network_gateway2', 'local_network_gateway2',
                        'connection_type', 'routing_weight', 'shared_key' ]

    def get_resource_url(self):
        return ("https://management.azure.com/subscriptions/{0}"
               "/resourceGroups/{1}/providers/Microsoft.Network"
               "/connections/{2}?api-version=2015-05-01-preview"
               .format(quote(self.subscription_id),
                       quote(self.resource_group),
                       quote(self.connection_name)))

    def mk_request(self, method):
        http_request = Request()
        http_request.url = self.get_resource_url()
        http_request.method = method
        http_request.headers['Content-Type'] = 'application/json'
        return http_request

    def _create_or_update(self, defn):
        info = {
            'location': defn.location,
            'tags': defn.tags,
            'properties': {
                'connectionType': defn.connection_type,
                'routingWeight': defn.routing_weight,
                'sharedKey': defn.shared_key,
            }
        }

        if defn.virtual_network_gateway1:
            info['properties']['virtualNetworkGateway1'] = { 'id': defn.virtual_network_gateway1 }
        if defn.virtual_network_gateway2:
            info['properties']['virtualNetworkGateway2'] = { 'id': defn.virtual_network_gateway2 }
        if defn.local_network_gateway2:
            info['properties']['localNetworkGateway2'] = { 'id': defn.local_network_gateway2 }

        http_request = self.mk_request('PUT')
        http_request.data = json.dumps(info)
        http_request.headers['Content-Length'] = len(http_request.data)
        response = self.nrpc().send_request(http_request)

        if response.status_code not in [200, 201]:
            raise AzureHttpError(response.content, response.status_code)

        self.state = self.UP
        self.copy_properties(defn)
        self.get_settled_resource()


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'resource_group')
        self.no_property_change(defn, 'connection_type')
        self.no_property_change(defn, 'virtual_network_gateway1')
        self.no_property_change(defn, 'virtual_network_gateway2')
        self.no_property_change(defn, 'local_network_gateway2')

        self.copy_mgmt_credentials(defn)
        self.connection_name = defn.connection_name
        self.resource_group = defn.resource_group

        if check:
            connection = self.get_settled_resource()
            if not connection:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(connection)
                self.handle_changed_property('location',
                                             normalize_location(connection.location),
                                             can_fix = False)
                self.handle_changed_property('tags', connection.tags)
                self.handle_changed_property('connection_type',
                                             connection.connection_type, can_fix = False)
                self.handle_changed_property('routing_weight',
                                             connection.routing_weight)
                # check key only if the user wants to manage it
                if defn.shared_key:
                    self.handle_changed_property('shared_key',
                                                connection.shared_key)
                self.handle_changed_property('virtual_network_gateway1',
                                             connection.virtual_network_gateway1 and
                                             connection.virtual_network_gateway1.id,
                                             can_fix = False)
                self.handle_changed_property('virtual_network_gateway2',
                                             connection.virtual_network_gateway2 and
                                             connection.virtual_network_gateway2.id,
                                             can_fix = False)
                self.handle_changed_property('local_network_gateway2',
                                             connection.local_network_gateway2 and
                                             connection.local_network_gateway2.id,
                                             can_fix = False)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a virtual network gateway connection that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0}...".format(self.full_name))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_local_network_gateway import AzureLocalNetworkGatewayState
        from nixops.resources.azure_virtual_network_gateway import AzureVirtualNetworkGatewayState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureLocalNetworkGatewayState) or
                     isinstance(r, AzureVirtualNetworkGatewayState) }
