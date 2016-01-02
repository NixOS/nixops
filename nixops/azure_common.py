# -*- coding: utf-8 -*-

import os
import re
import azure
import time
import threading

from nixops.util import attr_property, check_wait
import nixops.resources

from azure import *
from azure.servicemanagement import *

from azure.mgmt.common import SubscriptionCloudCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkResourceProviderClient
from azure.mgmt.storage import StorageManagementClient

import adal
import logging

logging.getLogger('python_adal').addHandler(logging.StreamHandler())


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

class ResourceDefinition(nixops.resources.ResourceDefinition):

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)

        res_name = self.get_option_value(xml, 'name', str)

        self.copy_option(xml, 'subscriptionId', str)
        self.copy_option(xml, 'certificatePath', str, empty = True, optional = True)
        self.authority_url = self.copy_option(xml, 'authority', str, empty = True, optional = True)
        self.copy_option(xml, 'user', str, empty = True, optional = True)
        self.copy_option(xml, 'password', str, empty = True, optional = True)

    def get_option_value(self, xml, name, type, optional = False,
                         empty = True, positive = False):
        types = { str: '/string', int: '/int', bool: '/bool', 'resource': '', 'strlist': '/list' }
        xml_ = xml.find("attrs")
        xml__= xml_ if xml_ is not None else xml
        elem = xml__.find("attr[@name='%s']%s" % (name, types[type]))

        if type == str:
            value = optional_string(elem)
        elif type == int:
            value = optional_int(elem)
        elif type == bool:
            value = optional_bool(elem)
        elif type == 'resource':
            value = ( optional_string(elem.find("string")) or
                      self.get_option_value(elem, 'name', str, optional = True) )
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
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='tags']/attrs/attr")
        }


class ResourceState(nixops.resources.ResourceState):

    subscription_id = attr_property("azure.subscriptionId", None)
    certificate_path = attr_property("azure.certificatePath", None)
    authority_url = attr_property("azure.authorityUrl", None)
    user = attr_property("azure.user", None)
    password = attr_property("azure.password", None)

    tokens_lock = threading.Lock()
    tokens = {}

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._sms = None
        self._rmc = None
        self._cmc = None
        self._nrpc = None
        self._smc = None

    def sms(self):
        if not self._sms:
            self._sms = ServiceManagementService(self.subscription_id, self.certificate_path)
        return self._sms

    def get_mgmt_credentials(self):
        with self.tokens_lock:
            token_id = "{0}|||{1}|||{2}".format(self.authority_url, self.user, self.password)
            if token_id in self.tokens:
                token = self.tokens[token_id]
            else:
                token = adal.acquire_token_with_username_password(
                            str(self.authority_url), str(self.user), str(self.password))
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

    @property
    def credentials_prefix(self):
        return "resources.{0}.$NAME".format(self.nix_name)

    def defn_subscription_id(self, defn):
        subscription_id = defn.subscription_id or os.environ.get('AZURE_SUBSCRIPTION_ID')
        if not subscription_id:
            raise Exception("please set '{0}.subscriptionId' or AZURE_SUBSCRIPTION_ID".format(self.credentials_prefix))
        return subscription_id

    def defn_certificate_path(self, defn):
        certificate_path = defn.certificate_path or os.environ.get('AZURE_CERTIFICATE_PATH')
        if not certificate_path:
            raise Exception("please set '{0}.certificatePath' or AZURE_CERTIFICATE_PATH".format(self.credentials_prefix))
        return certificate_path

    def defn_authority_url(self, defn):
        authority_url = defn.authority or os.environ.get('AZURE_AUTHORITY_URL')
        if not authority_url:
            raise Exception("please set '{0}.authority' or AZURE_AUTHORITY_URL".format(self.credentials_prefix))
        return authority_url

    def defn_user(self, defn):
        user = defn.user or os.environ.get('AZURE_USER')
        if not user:
            raise Exception("please set '{0}.user' or AZURE_USER".format(self.credentials_prefix))
        return user

    def defn_password(self, defn):
        password = defn.password or os.environ.get('AZURE_PASSWORD')
        if not password:
            raise Exception("please set '{0}.password' or AZURE_PASSWORD".format(self.credentials_prefix))
        return password

    def copy_credentials(self, defn):
        self.subscription_id = self.defn_subscription_id(defn)
        self.certificate_path = self.defn_certificate_path(defn)

    def copy_mgmt_credentials(self, defn):
        self.subscription_id = self.defn_subscription_id(defn)
        self.authority_url = self.defn_authority_url(defn)
        self.user = self.defn_user(defn)
        self.password = self.defn_password(defn)

    def is_deployed(self):
        return (self.state == self.UP)

    def no_change(self, condition, property_name):
        if self.is_deployed() and condition:
          raise Exception("cannot change the {0} of a deployed {1}"
                          .format(property_name, self.full_name))

    def no_property_change(self, defn, name):
        self.no_change(getattr(self, name) != getattr(defn, name), name.replace('_', ' ') )

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
                return self.confirm_destroy(abort = False)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
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
    # While resource is being destroyed, attempts at creating
    # a resource with the same name fail silently.
    # While resource is being created, attempts at destroying it also fail silently.
    # Thus we need to wait for certain resource states to settle.
    def is_settled(self, resource):
        return resource is None or (resource.state != 'Creating' and
                                    resource.state != 'Deleting')

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

    def finish_request(self, req, max_tries = 100):
        def check_req():
            return self.sms().get_operation_status(req.request_id).status != 'InProgress'
        try:
            check_wait(check_req, initial=1, max_tries=max_tries, exception=True)
        except:
            self.warn("operation on {0} failed".format(self.full_name))
            raise
        op_status = self.sms().get_operation_status(req.request_id)
        if op_status.status != 'Succeeded':
            raise Exception(op_status.error.__dict__)
