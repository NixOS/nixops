# -*- coding: utf-8 -*-

# Automatic provisioning of Azure DNS zones.

import os
import azure
import json
from requests import Request

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote # type: ignore

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState, ResId
from azure.common import AzureHttpError

from azure.mgmt.network import *

class AzureDNSZoneDefinition(ResourceDefinition):
    """Definition of an Azure DNS Zone"""

    @classmethod
    def get_type(cls):
        return "azure-dns-zone"

    @classmethod
    def get_resource_type(cls):
        return "azureDNSZones"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.dns_zone_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'resourceGroup', 'resource')
        self.copy_tags(xml)

    def show_type(self):
        return self.get_type()


class AzureDNSZoneState(ResourceState):
    """State of an Azure DNS Zone"""

    dns_zone_name = attr_property("azure.name", None)
    resource_group = attr_property("azure.resourceGroup", None)
    tags = attr_property("azure.tags", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-dns-zone"

    @property
    def resource_id(self):
        return self.dns_zone_name

    @property
    def full_name(self):
        return "Azure DNS zone '{0}'".format(self.resource_id)

    def is_settled(self, resource):
        return True

    def get_resource_url(self):
        return ("https://management.azure.com/subscriptions/{0}"
               "/resourceGroups/{1}/providers/Microsoft.Network"
               "/dnsZones/{2}?api-version=2015-05-04-preview"
               .format(quote(self.subscription_id),
                       quote(self.resource_group),
                       quote(self.dns_zone_name)))

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

    defn_properties = [ 'tags' ]

    def _create_or_update(self, defn):
        info = {
            "location": "global",
            "tags": defn.tags,
            "properties": { }
        }

        http_request = self.mk_request('PUT')
        http_request.data = json.dumps(info)
        http_request.headers['Content-Length'] = len(http_request.data)
        response = self.nrpc().send_request(http_request)        

        if response.status_code not in [200, 201]:
            raise AzureHttpError(response.content, response.status_code)

        self.state = self.UP
        self.copy_properties(defn)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_property_change(defn, 'resource_group')

        self.copy_mgmt_credentials(defn)
        self.dns_zone_name = defn.dns_zone_name
        self.resource_group = defn.resource_group

        if check:
            zone = self.get_settled_resource()
            if not zone:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('tags', zone['tags'])
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a DNS zone that already exists; "
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
