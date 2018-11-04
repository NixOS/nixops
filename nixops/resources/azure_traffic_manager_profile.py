# -*- coding: utf-8 -*-

# Automatic provisioning of Azure Traffic Manager profiles.

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

class AzureTrafficManagerProfileDefinition(ResourceDefinition):
    """Definition of an Azure Traffic Manager Profile"""

    @classmethod
    def get_type(cls):
        return "azure-traffic-manager-profile"

    @classmethod
    def get_resource_type(cls):
        return "azureTrafficManagerProfiles"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.profile_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_tags(xml)

        self.enable = "Enabled" if self.get_option_value(xml, 'enable', bool) else "Disabled"
        self.copy_option(xml, 'trafficRoutingMethod', str)

        dns_xml = xml.find("attrs/attr[@name='dns']")
        self.copy_option(dns_xml, 'relativeName', str)
        self.copy_option(dns_xml, 'ttl', int)

        mon_xml = xml.find("attrs/attr[@name='monitor']")
        self.copy_option(mon_xml, 'protocol', str)
        self.copy_option(mon_xml, 'port', int, positive = True)
        self.copy_option(mon_xml, 'path', str)

        self.endpoints = {
            _ep.get("name"): self._parse_endpoint(_ep)
            for _ep in xml.findall("attrs/attr[@name='endpoints']/attrs/attr")
        }

    def _parse_endpoint(self, xml):
        enabled = "Enabled" if self.get_option_value(xml, 'enable', bool) else "Disabled"
        weight = self.get_option_value(xml, 'weight', int,
                                       optional = (self.traffic_routing_method != 'Weighted'))
        priority = self.get_option_value(xml, 'priority', int,
                                         optional = (self.traffic_routing_method != 'Priority'))
        location = normalize_location(
                       self.get_option_value(xml, 'location', str,
                           optional = (self.traffic_routing_method != 'Performance')))
        return {
            'target': self.get_option_value(xml, 'target', str, empty = False),
            'endpointStatus': enabled,
            'weight': weight,
            'priority': priority,
            'endpointLocation': location,
        }


    def show_type(self):
        return self.get_type()


class AzureTrafficManagerProfieState(ResourceState):
    """State of an Azure Traffic Manager Profile"""

    profile_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    tags = attr_property("azure.tags", {}, 'json')

    enable = attr_property("azure.enable", None)
    traffic_routing_method = attr_property("azure.trafficRoutingMethod", None)

    relative_name = attr_property("azure.relativeName", None)
    ttl = attr_property("azure.ttl", None, int)

    protocol = attr_property("azure.protocol", None)
    port = attr_property("azure.port", None, int)
    path = attr_property("azure.path", None)

    endpoints = attr_property("azure.endpoints", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-traffic-manager-profile"

    @property
    def resource_id(self):
        return self.profile_name

    @property
    def full_name(self):
        return "Azure Traffic Manager profile '{0}'".format(self.resource_id)

    def is_settled(self, resource):
        return True

    def get_resource_url(self):
        return ("https://management.azure.com/subscriptions/{0}"
               "/resourceGroups/{1}/providers/Microsoft.Network"
               "/trafficManagerProfiles/{2}?api-version=2015-11-01"
               .format(quote(self.subscription_id),
                       quote(self.resource_group),
                       quote(self.profile_name)))

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
        if response.status_code != 200:
            raise AzureHttpError(response.content, response.status_code)

    defn_properties = [ 'tags', 'enable', 'traffic_routing_method',
                        'relative_name', 'ttl', 'protocol', 'port',
                        'path', 'endpoints' ]

    def _create_or_update(self, defn):
        info = {
            'location': "global",
            'tags': defn.tags,
            'properties': {
                'profileStatus': defn.enable,
                'trafficRoutingMethod': defn.traffic_routing_method,
                'dnsConfig': {
                    'relativeName': defn.relative_name,
                    'ttl': defn.ttl,
                },
                'monitorConfig': {
                    'protocol': defn.protocol,
                    'port': defn.port,
                    'path': defn.path,
                },
                'endpoints': [
                    { 'name': _n,
                      'type': "Microsoft.Network/TrafficManagerProfiles/ExternalEndpoints",
                      'properties': _ep
                    } for _n, _ep in defn.endpoints.iteritems()
                ],
            },
        }

        http_request = self.mk_request('PUT')
        http_request.data = json.dumps(info)
        http_request.headers['Content-Length'] = len(http_request.data)
        response = self.nrpc().send_request(http_request)        

        if response.status_code not in [200, 201]:
            raise AzureHttpError(response.content, response.status_code)

        self.state = self.UP
        self.copy_properties(defn)

        r = self.get_settled_resource() or {}
        fqdn = r.get('properties', {}).get('dnsConfig', {}).get('fqdn', None)
        self.log('FQDN: {0}'.format(fqdn))


    def handle_changed_endpoints(self, endpoints):
        def update_endpoints(k, v):
            x = self.endpoints
            if v == None:
                x.pop(k, None)
            else:
                x[k] = v
            self.endpoints = x

        for _ep in endpoints:
            _ep_name = next((_n for _n, _x in self.endpoints.iteritems()
                                if _n == _ep.get('name', None)),
                            None)
            if _ep_name is None:
                self.warn("found unexpected endpoint {0}".format(_ep.get('name', None)))
                update_endpoints(_ep.get('name', None), {"dummy": True})
        for _name, _s_ep in self.endpoints.iteritems():
            if _s_ep.get("dummy", False): continue
            ep_res_name = "endpoint {0}".format(_name)
            ep = next((_r for _r in endpoints
                          if _r.get('name', None) == _name),
                      None)
            if ep is None:
                self.warn("{0} has been deleted behind our back".format(ep_res_name))
                update_endpoints(_name, None)
                continue
            properties = ep.get('properties', {})
            self.handle_changed_dict(_s_ep, 'target',
                                     properties.get('target', None),
                                     resource_name = ep_res_name)
            self.handle_changed_dict(_s_ep, 'endpointStatus',
                                     properties.get('endpointStatus', None),
                                     resource_name = ep_res_name)
            if self.traffic_routing_method == 'Weighted':
                self.handle_changed_dict(_s_ep, 'weight',
                                         properties.get('weight', None),
                                         resource_name = ep_res_name)
            if self.traffic_routing_method == 'Priority':
                self.handle_changed_dict(_s_ep, 'priority',
                                         properties.get('priority', None),
                                         resource_name = ep_res_name)
            if self.traffic_routing_method == 'Performance':
                self.handle_changed_dict(_s_ep, 'endpointLocation',
                                         normalize_location(
                                             properties.get('endpointLocation', None)),
                                         resource_name = ep_res_name)
            update_endpoints(_name, _s_ep)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.profile_name = defn.profile_name
        self.resource_group = defn.resource_group

        if check:
            profile = self.get_settled_resource()
            if not profile:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('tags', profile.get('tags', {}))

                properties = profile.get('properties', {})
                self.handle_changed_property('enable', properties.get('profileStatus', None))
                self.handle_changed_property('traffic_routing_method',
                                             properties.get('trafficRoutingMethod', None))
                dns = properties.get('dnsConfig', {})
                self.handle_changed_property('relative_name',
                                             dns.get('relativeName', None))
                self.handle_changed_property('ttl', dns.get('ttl', None))
                monitor = properties.get('monitorConfig', {})
                self.handle_changed_property('protocol',
                                             monitor.get('protocol', None))
                self.handle_changed_property('port',
                                             monitor.get('port', None))
                self.handle_changed_property('path',
                                             monitor.get('path', None))
                self.handle_changed_endpoints(properties.get('endpoints', []))
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a traffic manager profile that already exists; "
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
