# -*- coding: utf-8 -*-

import os
import re
import azure
import time
import threading
import requests

from nixops.util import attr_property, check_wait
import nixops.resources

from typing import Dict
from azure import *

from azure.mgmt.common import SubscriptionCloudCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkResourceProviderClient
from azure.mgmt.storage import StorageManagementClient

from azure.storage.blob import BlobService
from azure.storage.queue import QueueService
from azure.storage.table import TableService
from azure.storage.file import FileService

from azure.storage.models import SignedIdentifiers, SignedIdentifier, AccessPolicy

import adal
import logging

logging.getLogger('python_adal').addHandler(logging.NullHandler())


def optional_string(elem):
    return (elem.get("value") if elem is not None else None)

def optional_int(elem):
    return (int(elem.get("value")) if elem is not None else None)

def optional_bool(elem):
    return (elem.get("value") == "true" if elem is not None else None)

def ensure_not_empty(value, name):
    if not value:
        raise Exception("{0} must not be empty".format(name))

def ensure_positive(value, name):
    if value <= 0:
        raise Exception("{0} must be a positive integer".format(name))

def normalize_location(location):
    return None if location is None else location.lower().replace(' ', '')

class ResId(dict):
    def __init__(self, base, **kwargs):
        self.update(self.parse(base) or {})
        self.update(kwargs)

    def __str__(self):
        return self.id or ""

    # method azure mgmt calls this to get resource references
    @property
    def id(self):
        if all(self.get(x, None)
               for x in ['subscription', 'group', 'provider', 'type', 'resource']):
            res_str = ( "/subscriptions/{0}/resourceGroups/{1}"
                        "/providers/{2}/{3}/{4}"
                        .format(self['subscription'], self['group'],
                                self['provider'], self['type'],
                                self['resource'] ))
        else:
            return None
        if self.get('subresource', None) and self.get('subtype', None):
            res_str += "/{0}/{1}".format(self['subtype'], self['subresource'])
        return res_str

    @property
    def reference_uri(self):
        return self.id

    @classmethod
    def parse(cls, r_id):
        match = re.match(r'/subscriptions/(?P<subscription>.+?)/resourceGroups/(?P<group>.+?)'
                          '/providers/(?P<provider>.+?)/(?P<type>.+?)/(?P<resource>.+?)'
                          '(/(?P<subtype>.+?)/(?P<subresource>.+?))?$', str(r_id))
        return match and match.groupdict()

    nix_type_conv = {
        'azure-availability-set': { 'provider': 'Microsoft.Compute', 'type': 'availabilitySets' },
        'azure-load-balancer': { 'provider': 'Microsoft.Network', 'type': 'loadBalancers' },
        'azure-reserved-ip-address': {'provider': 'Microsoft.Network', 'type': 'publicIPAddresses' },
        'azure-virtual-network': {'provider':'Microsoft.Network', 'type': 'virtualNetworks' },
        'azure-network-security-group': { 'provider':'Microsoft.Network', 'type': 'networkSecurityGroups' },
        'azure-dns-zone': { 'provider':'Microsoft.Network', 'type': 'dnsZones' },
        'azure-local-network-gateway': { 'provider':'Microsoft.Network', 'type': 'localNetworkGateways' },
        'azure-virtual-network-gateway': { 'provider':'Microsoft.Network', 'type': 'virtualNetworkGateways' },
    }


class ResourceDefinitionBase(nixops.resources.ResourceDefinition):
    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        res_name = self.get_option_value(xml, 'name', str)

    def get_option_value(self, xml, name, type, optional = False,
                         empty = True, positive = False):
        types = { str: '/string', int: '/int', bool: '/bool', 'resource': '', 'res-id': '', 'strlist': '/list' }
        xml_ = xml.find("attrs")
        xml__= xml_ if xml_ is not None else xml
        elem = xml__.find("attr[@name='%s']%s" % (name, types[type]))
        if elem is None:
            value = None
        elif type == str:
            value = optional_string(elem)
        elif type == int:
            value = optional_int(elem)
        elif type == bool:
            value = optional_bool(elem)
        elif type == 'resource':
            value = ( optional_string(elem.find("string")) or
                      self.get_option_value(elem, 'name', str, optional = True) )
        elif type == 'res-id':
            _type = self.get_option_value(elem, '_type', str, optional = True)
            res_type = ResId.nix_type_conv.get(_type, {'provider': None, 'type': None })
            value = ( optional_string(elem.find("string")) or
                      ResId("",
                            subscription = self.get_subscription_id(),
                            provider = res_type['provider'],
                            type = res_type['type'],
                            resource = self.get_option_value(elem, 'name', str, optional = True),
                            group = self.get_option_value(elem, 'resourceGroup', 'resource', optional = True)
                           ).id )
        elif type == 'strlist':
            value = sorted( [ s.get("value")
                              for s in elem.findall("string") ] ) if elem is not None else None

        if not optional and value is None:
            raise Exception("{0}: option {1} must be set".format(self.name, name))

        if not empty and not value:
            raise Exception("{0}: {1} must not be empty".format(self.name, name))

        if positive and value is not None and (value <= 0):
            raise Exception("{0}: {1} must be a positive integer".format(self.name, name))
        return value

    # store the option value in a property, following the naming conventions
    # by converting "optionName" to "option_name"
    def copy_option(self, xml, name, type, optional = False,
                         empty = True, positive = False):
      setattr(self, re.sub(r'([a-z])([A-Z])',r'\1_\2', name).lower(),
              self.get_option_value(xml, name, type, optional = optional,
                                    empty = empty, positive = positive) )

    def copy_tags(self, xml):
        self.tags = {
            tag.get("name"): tag.find("string").get("value")
            for tag in xml.findall("attrs/attr[@name='tags']/attrs/attr")
        }


class ResourceDefinition(ResourceDefinitionBase):

    def __init__(self, xml):
        ResourceDefinitionBase.__init__(self, xml)

        self.copy_credentials(xml)

    def copy_credentials(self, xml):
        self.copy_option(xml, 'subscriptionId', str)
        self.copy_option(xml, 'authority', str, empty = True, optional = True)
        self.copy_option(xml, 'identifierUri', str, empty = True, optional = True)
        self.copy_option(xml, 'appId', str, empty = True, optional = True)
        self.copy_option(xml, 'appKey', str, empty = True, optional = True)

    @property
    def credentials_prefix(self):
        return "resources.{0}.{1}".format(self.get_resource_type(), self.name)

    def get_subscription_id(self):
        subscription_id = self.subscription_id or os.environ.get('AZURE_SUBSCRIPTION_ID')
        if not subscription_id:
            raise Exception("please set '{0}.subscriptionId' or AZURE_SUBSCRIPTION_ID".format(self.credentials_prefix))
        return subscription_id

    def get_authority_url(self):
        authority_url = self.authority or os.environ.get('AZURE_AUTHORITY_URL')
        if not authority_url:
            raise Exception("please set '{0}.authority' or AZURE_AUTHORITY_URL".format(self.credentials_prefix))
        return authority_url

    def get_identifier_uri(self):
        identifier_uri = self.identifier_uri or os.environ.get('AZURE_ACTIVE_DIR_APP_IDENTIFIER_URI')
        if not identifier_uri:
            raise Exception("please set '{0}.identifierUri' or AZURE_ACTIVE_DIR_APP_IDENTIFIER_URI".format(self.credentials_prefix))
        return identifier_uri;

    def get_app_id(self):
        app_id = self.app_id or os.environ.get('AZURE_ACTIVE_DIR_APP_ID')
        if not app_id:
            raise Exception("please set '{0}.appId' or AZURE_ACTIVE_DIR_APP_ID".format(self.credentials_prefix))
        return app_id

    def get_app_key(self):
        app_key = self.app_key or os.environ.get('AZURE_ACTIVE_DIR_APP_KEY')
        if not app_key:
            raise Exception("please set '{0}.appKey' or AZURE_ACTIVE_DIR_APP_KEY".format(self.credentials_prefix))
        return app_key

    def copy_location(self, xml):
        self.location = normalize_location(
                            self.get_option_value(xml, 'location', str, empty = False))


class StorageResourceDefinition(ResourceDefinitionBase):

    def __init__(self, xml):
        ResourceDefinitionBase.__init__(self, xml)

        self.copy_option(xml, 'accessKey', str, optional = True)

    def copy_signed_identifiers(self, xml):
        self.signed_identifiers = {
            s_id.get("name"): {
                'start': self.get_option_value(s_id, 'start', str),
                'expiry': self.get_option_value(s_id, 'expiry', str),
                'permissions': self.get_option_value(s_id, 'permissions', str),
            }
            for s_id in xml.findall("attrs/attr[@name='signedIdentifiers']/attrs/attr")
        }

    def copy_metadata(self, xml):
        self.metadata = {
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='metadata']/attrs/attr")
        }


class ResourceState(nixops.resources.ResourceState):

    subscription_id = attr_property("azure.subscriptionId", None)
    authority_url = attr_property("azure.authorityUrl", None)
    identifier_uri = attr_property("azure.identifierUri", None)
    app_id = attr_property("azure.appId", None)
    app_key = attr_property("azure.appKey", None)

    tokens_lock = threading.Lock()
    tokens = {}  # type: Dict[str, Dict]

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._rmc = None
        self._cmc = None
        self._nrpc = None
        self._smc = None

    def get_mgmt_credentials(self):
        with self.tokens_lock:
            token_id = "{0}|||{1}|||{2}".format(self.authority_url, self.app_id, self.app_key)
            if token_id in self.tokens:
                token = self.tokens[token_id]
            else:
                try:
                    context = adal.AuthenticationContext(self.authority_url)
                    token = context.acquire_token_with_client_credentials(
                        str(self.identifier_uri),
                        str(self.app_id),
                        str(self.app_key))
                except Exception as e:
                    e.args = ("Auth failure: {0}".format(e.args[0]),) + e.args[1:] 
                    raise
                self.tokens[token_id] = token
        return SubscriptionCloudCredentials(self.subscription_id, token['accessToken'])

    def rmc(self):
        if not self._rmc:
            self._rmc = ResourceManagementClient(self.get_mgmt_credentials())
        return self._rmc

    def cmc(self):
        if not self._cmc:
            self.rmc().providers.register('Microsoft.Compute')
            self._cmc = ComputeManagementClient(self.get_mgmt_credentials())
            self._cmc.long_running_operation_initial_timeout = 3
            self._cmc.long_running_operation_retry_timeout = 5
        return self._cmc

    def nrpc(self):
        if not self._nrpc:
            self.rmc().providers.register('Microsoft.Network')
            self._nrpc = NetworkResourceProviderClient(self.get_mgmt_credentials())
        return self._nrpc

    def smc(self):
        if not self._smc:
            self.rmc().providers.register('Microsoft.Storage')
            self._smc = StorageManagementClient(self.get_mgmt_credentials())
        return self._smc


    def copy_mgmt_credentials(self, defn):
        self.subscription_id = defn.get_subscription_id()
        self.authority_url = defn.get_authority_url()
        self.identifier_uri = defn.get_identifier_uri()
        self.app_id = defn.get_app_id()
        self.app_key = defn.get_app_key()

    def is_deployed(self):
        return (self.state == self.UP)

    def is_failed(self, resource):
        return resource.provisioning_state == 'Failed'

    def warn_if_failed(self, resource):
        if self.is_failed(resource):
            self.warn("resource exists, but is in a failed state")

    def no_change(self, condition, property_name):
        if self.is_deployed() and condition:
          raise Exception("cannot change the {0} of a deployed {1}"
                          .format(property_name, self.full_name))

    def no_property_change(self, defn, name):
        self.no_change(getattr(self, name) != getattr(defn, name), name.replace('_', ' ') )

    def no_subscription_id_change(self, defn):
        self.no_change(self.subscription_id != defn.get_subscription_id(), 'subscription ID')

    def no_location_change(self, defn):
        self.no_change(normalize_location(self.location) !=
                       normalize_location(defn.location),
                       'location')

    def warn_missing_resource(self):
        if self.state == self.UP:
            self.warn("{0} is supposed to exist, but is missing; recreating...".format(self.full_name))
            self.state = self.MISSING

    def warn_if_changed(self, expected_state, actual_state, name,
                        resource_name = None, can_fix = True):
        if expected_state != actual_state:
            self.warn("{0} {1} has changed to '{2}'; expected it to be '{3}'{4}"
                      .format(resource_name or self.full_name,
                              name, actual_state, expected_state,
                              "" if can_fix else "; cannot fix this automatically"))
        return actual_state

    # use warn_if_changed for a very typical use case of dealing
    # with changed properties which are stored in attributes
    # with user-friendly names
    def handle_changed_property(self, name, actual_state,
                                property_name = None, can_fix = True):
        self.warn_if_changed(getattr(self, name), actual_state,
                             property_name or name.replace('_', ' '),
                             can_fix = can_fix)
        if can_fix:
            setattr(self, name, actual_state)

    # use warn_if_changed for a very typical use case of dealing
    # with changed properties which are stored in dictionaries
    # with user-friendly names
    def handle_changed_dict(self, resource, name, actual_state,
                                property_name = None, resource_name = None, can_fix = True):
        self.warn_if_changed(resource[name], actual_state,
                             property_name or name.replace('_', ' '),
                             resource_name = resource_name,
                             can_fix = can_fix)
        if can_fix:
            resource[name] = actual_state

    def warn_not_supposed_to_exist(self, resource_name = None,
                              valuable_data = False, valuable_resource = False):
        valuables = " or ".join(filter(None, [valuable_data and "data", valuable_resource and "resource"]))
        valuable_msg = ( "; however, this also could be a resource name collision, "
                         "and valuable {0} could be lost; before proceeding, "
                         "please ensure that this isn't so".format(valuables)
                         if valuables else "" )
        self.warn("{0} exists, but isn't supposed to; probably, this is the result "
                  "of a botched creation attempt and can be fixed by deletion{1}"
                  .format(resource_name or self.full_name, valuable_msg))


    def confirm_destroy(self, res_name = None, abort = True):
        if self.depl.logger.confirm("are you sure you want to destroy {0}?".format(res_name or self.full_name)):
            self.log("destroying...")
            self.destroy_resource()
            return True
        else:
            if abort:
                raise Exception("can't proceed further")
            else:
                return False

    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                resource = self.get_settled_resource()
                if resource is None:
                    self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
                else:
                    return self.confirm_destroy(abort = False)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
            except azure.common.AzureHttpError as e:
                if e.status_code == 204:
                    self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
                else:
                    raise
        return True


    # API to handle copying properties from definition to state
    # after resource is created or updated and checking that
    # the state is out of sync with the definition
    def copy_properties(self, defn):
        for attr in self.defn_properties:
            setattr(self, attr, getattr(defn, attr))

    def properties_changed(self, defn):
        return any( getattr(self, attr) != getattr(defn, attr)
                    for attr in self.defn_properties )


    # Certain resources are provisioned and destroyed asynchronously.
    # While resource is being created or destroyed, attempts at
    # creating, updating or destroying a resource with the same name may fail.
    # Thus we need to wait for certain resource states to settle.
    def is_settled(self, resource):
        return resource is None or (resource.provisioning_state in ['Succeeded', 'Failed'])

    def ensure_settled(self):
        def check_settled():
            resource = self.get_resource()
            return self.is_settled(resource)

        check_wait(check_settled, initial=1, max_tries=100, exception=True)

    def get_settled_resource(self, initial=1, factor=1, max_tries=60):
        def _get_resource():
            try:
                return self.get_resource()
            except Exception as e:
                self.log("Failed getting access to {0}".format(self.full_name))
                raise
        wait = initial
        tries = 0
        resource = _get_resource()

        while tries < max_tries and not self.is_settled(resource):
            wait = wait * factor
            tries = tries + 1
            if tries == max_tries:
                raise Exception("resource failed to settle")
            time.sleep(wait)
            resource = _get_resource()
        return resource

    def get_resource_state(self, cls, name):
        if cls is None:
            return None
        if not name:
            return None
        return next((r for r in self.depl.resources.values()
                       if isinstance(r, cls) and getattr(r, 'resource_id', None) == name), None)

    # retrieve the resource and complain to the user if it doesn't exist
    def get_settled_resource_assert_exists(self):
        res = self.get_settled_resource()
        if res is None:
            raise Exception("{0} has been deleted behind our back; "
                            "please run 'deploy --check' to fix this"
                            .format(self.full_name))
        return res


class StorageResourceState(ResourceState):

    access_key = attr_property("azure.accessKey", None)

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)
        self._bs = None
        self._qs = None
        self._ts = None
        self._fs = None

    def get_resource(self):
        try:
            return self.get_resource_allow_exceptions()
        except requests.exceptions.ConnectionError:
            self.warn("connection error: either storage doesn't exist and thus this resource "
                      "doesn't exist as well, the storage domain name is in negative DNS cache "
                      "or your network connection is down; you must either re-deploy the storage, "
                      "drop DNS cache or delete this resource manually; aborting to avoid data loss")
            raise
        except azure.common.AzureMissingResourceHttpError:
            return None

    def bs(self):
        if not self._bs:
            self._bs = BlobService(self.get_storage_name(), self.get_key())
        return self._bs

    def qs(self):
        if not self._qs:
            self._qs = QueueService(self.get_storage_name(), self.get_key())
        return self._qs

    def ts(self):
        if not self._ts:
            self._ts = TableService(self.get_storage_name(), self.get_key())
        return self._ts

    def fs(self):
        if not self._fs:
            self._fs = FileService(self.get_storage_name(), self.get_key())
        return self._fs


    # Signed Identifiers handling helpers
    def _signed_identifiers_to_dict(self, signed_identifiers):
        return {
            s_id.id: {
              'start': s_id.access_policy.start,
              'expiry': s_id.access_policy.expiry,
              'permissions': s_id.access_policy.permission,
            }
            for s_id in signed_identifiers.signed_identifiers
        }

    def _dict_to_signed_identifiers(self, signed_identifiers):
        result = SignedIdentifiers()
        for _id, policy in signed_identifiers.iteritems():
            identifier = SignedIdentifier()
            identifier.id = _id
            identifier.access_policy = AccessPolicy(
                start = policy['start'],
                expiry = policy['expiry'],
                permission = policy['permissions']
            )
            result.signed_identifiers.append(identifier)
        return result

    def handle_changed_signed_identifiers(self, signed_identifiers):
        self.handle_changed_property('signed_identifiers',
                                     self._signed_identifiers_to_dict(signed_identifiers))

    def handle_changed_metadata(self, resource_with_metadata):
        metadata = { k[10:] : v
                      for k, v in resource_with_metadata.items()
                      if k.startswith('x-ms-meta-') }
        self.handle_changed_property('metadata', metadata)
