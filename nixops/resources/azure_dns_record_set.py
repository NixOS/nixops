# -*- coding: utf-8 -*-

# Automatic provisioning of Azure DNS record sets.

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

class AzureDNSRecordSetDefinition(ResourceDefinition):
    """Definition of an Azure DNS Record Set"""

    @classmethod
    def get_type(cls):
        return "azure-dns-record-set"

    @classmethod
    def get_resource_type(cls):
        return "azureDNSRecordSets"

    def __init__(self, xml, config):
        ResourceDefinition.__init__(self, xml)

        self.dns_record_set_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'dnsZone', 'res-id')
        self.copy_option(xml, 'recordType', str, empty = False)
        self.copy_tags(xml)
        self.properties = config['properties']

    def show_type(self):
        return self.get_type()


class AzureDNSRecordSetState(ResourceState):
    """State of an Azure DNS Record Set"""

    dns_record_set_name = attr_property("azure.name", None)
    dns_zone = attr_property("azure.dnsZone", None)
    record_type = attr_property("azure.recordType", None)
    tags = attr_property("azure.tags", {}, 'json')
    properties = attr_property("azure.properties", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-dns-record-set"

    @property
    def resource_id(self):
        return self.dns_record_set_name

    @property
    def full_name(self):
        return "Azure DNS record set '{0}'".format(self.resource_id)

    def is_settled(self, resource):
        return True

    def get_resource_url(self):
        return ("https://management.azure.com"
                "{0}/{1}/{2}?api-version=2015-05-04-preview"
                .format(quote(self.dns_zone),
                        quote(self.record_type),
                        quote(self.dns_record_set_name)))

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

    defn_properties = [ 'tags', 'properties' ]

    def _create_or_update(self, defn):
        info = {
            "location": "global",
            "tags": defn.tags,
            "properties": defn.properties
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
        self.no_property_change(defn, 'dns_zone')
        self.no_property_change(defn, 'record_type')

        self.copy_mgmt_credentials(defn)
        self.dns_record_set_name = defn.dns_record_set_name
        self.dns_zone = defn.dns_zone
        self.record_type = defn.record_type

        if check:
            rset = self.get_settled_resource()
            if not rset:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('tags', rset['tags'])
                self.handle_changed_property('properties', rset['properties'])
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a DNS record set that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0}...".format(self.full_name))
            self._create_or_update(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self._create_or_update(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_dns_zone import AzureDNSZoneState
        return {r for r in resources
                  if isinstance(r, AzureResourceGroupState) or isinstance(r, AzureDNSZoneState) }
