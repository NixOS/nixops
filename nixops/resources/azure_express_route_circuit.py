# -*- coding: utf-8 -*-

# Automatic provisioning of Azure ExpressRoute circuits.

import os
import azure
import json
from requests import Request

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote  # type: ignore

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location
from azure.common import AzureHttpError

from azure.mgmt.network import *

class AzureExpressRouteCircuitDefinition(ResourceDefinition):
    """Definition of an Azure ExpressRoute Circuit"""

    @classmethod
    def get_type(cls):
        return "azure-express-route-circuit"

    @classmethod
    def get_resource_type(cls):
        return "azureExpressRouteCircuits"

    def __init__(self, xml, config):
        ResourceDefinition.__init__(self, xml)

        self.circuit_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_location(xml)
        self.copy_tags(xml)

        sku_xml = xml.find("attrs/attr[@name='sku']")
        self.copy_option(sku_xml, 'tier', str)
        self.copy_option(sku_xml, 'family', str)

        self.copy_option(xml, 'serviceProviderName', str, empty = False)
        self.copy_option(xml, 'peeringLocation', str, empty = False)
        self.copy_option(xml, 'bandwidth', int, positive = True)

        self.peerings = config['peerings']

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureExpressRouteCircuitState(ResourceState):
    """State of an Azure ExpressRoute Circuit"""

    circuit_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    location = attr_property("azure.location", None)
    tags = attr_property("azure.tags", {}, 'json')

    tier = attr_property("azure.tier", None)
    family = attr_property("azure.family", None)

    service_provider_name = attr_property("azure.serviceProviderName", None)
    peering_location = attr_property("azure.peeringLocation", None)
    bandwidth = attr_property("azure.bandwidth", None, int)
    peerings = attr_property("azure.peerings", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-express-route-circuit"

    @property
    def resource_id(self):
        return self.circuit_name

    @property
    def full_name(self):
        return "Azure ExpressRoute circuit '{0}'".format(self.resource_id)

    def is_settled(self, resource):
        return resource is None or (resource.get('properties', {})
                                            .get('provisioningState', None) in ['Succeeded', 'Failed'])

    def is_failed(self, resource):
        return resource.get('properties', {}).get('provisioningState', None) == 'Failed'

    def get_resource_url(self):
        return ("https://management.azure.com/subscriptions/{0}"
               "/resourceGroups/{1}/providers/Microsoft.Network"
               "/expressRouteCircuits/{2}?api-version=2015-06-15"
               .format(quote(self.subscription_id),
                       quote(self.resource_group),
                       quote(self.circuit_name)))

    def mk_request(self, method):
        http_request = Request()
        http_request.url = self.get_resource_url()
        http_request.method = method
        http_request.headers['Content-Type'] = 'application/json'
        return http_request

    def get_resource(self):
        response = self.nrpc().send_request(self.mk_request('GET'))
        if response.status_code == 200:
            return json.loads(response.content.decode())
        else:
            return None

    def destroy_resource(self):
        response = self.nrpc().send_request(self.mk_request('DELETE'))
        if response.status_code not in [200, 202, 204]:
            raise AzureHttpError(response.content, response.status_code)
        self.get_settled_resource() # wait for the delete operation to finish

    defn_properties = [ 'tags', 'location', 'tier', 'family',
                        'service_provider_name', 'peering_location',
                        'bandwidth', 'peerings' ]

    def _create_or_update(self, defn):
        info = {
            'location': defn.location,
            'tags': defn.tags,
            'sku': {
                'name': "{0}_{1}".format(defn.tier, defn.family),
                'tier': defn.tier,
                'family': defn.family,
            },
            'properties': {
                'serviceProviderProperties': {
                    'serviceProviderName': defn.service_provider_name,
                    'peeringLocation': defn.peering_location,
                    'bandwidthInMbps': defn.bandwidth,
                },
                'peerings': [
                    { 'name': _n,
                      'properties': _p,
                    } for _n, _p in defn.peerings.iteritems()
                ],
            },
        }

        http_request = self.mk_request('PUT')
        http_request.data = json.dumps(info)
        http_request.headers['Content-Length'] = len(http_request.data)
        response = self.nrpc().send_request(http_request)        

        if response.status_code not in [200, 201, 202]:
            raise AzureHttpError(response.content, response.status_code)

        self.get_settled_resource()
        self.state = self.UP
        self.copy_properties(defn)


    def handle_changed_peerings(self, peerings):
        def update_peerings(k, v):
            x = self.peerings
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.peerings = x

        for _p in peerings:
            _p_name = next((_n for _n, _x in self.peerings.iteritems()
                               if _n == _p.get('name', None)),
                            None)
            if _p_name is None:
                self.warn("found unexpected peering {0}".format(_p.get('name', None)))
                update_peerings(_p.get('name', None), {"dummy": True})
        for _name, _s_p in self.peerings.iteritems():
            if _s_p.get("dummy", False): continue
            p_res_name = "peering {0}".format(_name)
            p = next((_r for _r in peerings
                         if _r.get('name', None) == _name),
                     None)
            if p is None:
                self.warn("{0} has been deleted behind our back".format(p_res_name))
                update_peerings(_name, None)
                continue
            properties = p.get('properties', {})
            # only check the properties that the user has specified explicitly
            for prop_name in _s_p.keys():
                self.handle_changed_dict(_s_p, prop_name,
                                         properties.get(prop_name, None),
                                         resource_name = p_res_name)
            update_peerings(_name, _s_p)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'resource_group')
        self.no_location_change(defn)

        self.copy_mgmt_credentials(defn)
        self.circuit_name = defn.circuit_name
        self.resource_group = defn.resource_group

        if check:
            circuit = self.get_settled_resource()
            if not circuit:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_failed(circuit)
                self.handle_changed_property('tags', circuit.get('tags', {}))
                self.handle_changed_property('location',
                                             normalize_location(circuit.get('location', None)),
                                             can_fix = False)
                sku = circuit.get('sku', {})
                self.handle_changed_property('tier', sku.get('tier', None))
                self.handle_changed_property('family', sku.get('family', None))
                properties = circuit.get('properties', {})
                provider = properties.get('serviceProviderProperties', {})
                self.handle_changed_property('service_provider_name',
                                             provider.get('serviceProviderName', None))
                self.handle_changed_property('peering_location',
                                             provider.get('peeringLocation', None))
                self.handle_changed_property('bandwidth',
                                             provider.get('bandwidthInMbps', None))
                self.handle_changed_peerings(properties.get('peerings', []))
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating an express route circuit that already exists; "
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
                  if isinstance(r, AzureResourceGroupState) }
