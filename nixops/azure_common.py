# -*- coding: utf-8 -*-

import os
import re
import azure
import time

from nixops.util import attr_property, check_wait
import nixops.resources

from azure import *
from azure.servicemanagement import *

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
        self.copy_option(xml, 'certificatePath', str)

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
            raise Exception("option {0} must be set".format(name))

        if not empty:
            ensure_not_empty(value, name)
        if positive:
            ensure_positive(value, name)
        return value

    # store the option value in a property, following the naming conventions
    # by converting "optionName" to "option_name"
    def copy_option(self, xml, name, type, optional = False,
                         empty = True, positive = False):
      setattr(self, re.sub(r'([a-z])([A-Z])',r'\1_\2', name).lower(),
              self.get_option_value(xml, name, type, optional = optional,
                                    empty = empty, positive = positive) )


class ResourceState(nixops.resources.ResourceState):

    subscription_id = attr_property("azure.subscriptionId", None)
    certificate_path = attr_property("azure.certificatePath", None)

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._sms = None

    def sms(self):
        if not self._sms:
            self._sms = ServiceManagementService(self.subscription_id, self.certificate_path)
        return self._sms

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

    def copy_credentials(self, defn):
        self.subscription_id = self.defn_subscription_id(defn)
        self.certificate_path = self.defn_certificate_path(defn)

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
                resource = self.get_resource()
                return self.confirm_destroy(abort = False)
            except azure.WindowsAzureMissingResourceError:
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
        return resource.state != 'Creating' and resource.state != 'Deleting'

    def ensure_settled(self):
        def check_settled():
            try:
                resource = self.get_resource()
                return self.is_settled(resource)
            except azure.WindowsAzureMissingResourceError:
                return True

        check_wait(check_settled, initial=1, max_tries=100, exception=True)

    def get_settled_resource(self, initial=1, factor=1, max_tries=60):
        wait = initial
        tries = 0
        resource = self.get_resource()
        while tries < max_tries and not self.is_settled(resource):
            wait = wait * factor
            tries = tries + 1
            if tries == max_tries:
                raise Exception("resource failed to settle")
            time.sleep(wait)
            resource = self.get_resource()
        return resource
