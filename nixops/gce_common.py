# -*- coding: utf-8 -*-

import os
import re

from nixops.util import attr_property
import nixops.resources

from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver


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
        if len(res_name)>63 or re.match('[a-z]([-a-z0-9]{0,61}[a-z0-9])?$', res_name) is None:
            raise Exception("Resource name ‘{0}‘ must be 1-63 characters long and "
              "match the regular expression [a-z]([-a-z0-9]*[a-z0-9])? which "
              "means the first character must be a lowercase letter, and all "
              "following characters must be a dash, lowercase letter, or digit, "
              "except the last character, which cannot be a dash.".format(res_name))

        self.copy_option(xml, 'project', str)
        self.copy_option(xml, 'serviceAccount', str)
        self.access_key_path = self.get_option_value(xml, 'accessKey', str)

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

    project = attr_property("gce.project", None)
    service_account = attr_property("gce.serviceAccount", None)
    access_key_path = attr_property("gce.accessKey", None)

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def connect(self):
        if not self._conn:
            self._conn = get_driver(Provider.GCE)(self.service_account, self.access_key_path, project = self.project)
        return self._conn

    @property
    def credentials_prefix(self):
        return "resources.{0}.$NAME".format(self.nix_name)

    def defn_project(self, defn):
        project = defn.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘{0}.project’ or $GCE_PROJECT".format(self.credentials_prefix))
        return project

    def defn_service_account(self, defn):
        service_account = defn.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘{0}.serviceAccount’ or $GCE_SERVICE_ACCOUNT".format(self.credentials_prefix))
        return service_account

    def defn_access_key_path(self, defn):
        access_key_path = defn.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘{0}.accessKey’ or $ACCESS_KEY_PATH".format(self.credentials_prefix))
        return access_key_path

    def copy_credentials(self, defn):
        self.project = self.defn_project(defn)
        self.service_account = self.defn_service_account(defn)
        self.access_key_path = self.defn_access_key_path(defn)

    def no_change(self, condition, property_name):
        if self.state == self.UP and condition:
          raise Exception("Cannot change the {0} of a deployed {1}"
                          .format(property_name, self.full_name))

    def no_project_change(self, defn):
        self.no_change(self.project != self.defn_project(defn), 'project')

    def no_region_change(self, defn):
        self.no_change(self.region != defn.region, 'region')

    def warn_missing_resource(self):
        if self.state == self.UP:
            self.warn("{0} is supposed to exist, but is missing. Recreating...".format(self.full_name))
            self.state = self.MISSING

    def confirm_destroy(self, resource, res_name, abort = True):
        if self.depl.logger.confirm("Are you sure you want to destroy {0}?".format(res_name)):
            self.log_start("destroying...")
            resource.destroy()
            self.log_end("done.")
            return True
        else:
            if abort:
                raise Exception("Can't proceed further.")
            else:
                return False

    def warn_if_changed(self, expected_state, actual_state, name,
                        resource_name = None, can_fix = True):
        if expected_state != actual_state:
            self.warn("{0} {1} has changed to '{2}'. Expected it to be '{3}'.{4}"
                      .format(resource_name or self.full_name,
                              name, actual_state, expected_state,
                              "" if can_fix else "Cannot fix this automatically."))
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
        valuable_msg = ( " However, this also could be a resource name collision, "
                         "and valuable {0} could be lost. Before proceeding, "
                         "please ensure that this isn't so.".format(valuables)
                         if valuables else "" )
        self.warn("{0} exists, but isn't supposed to. Probably, this is the result "
                  "of a botched creation attempt and can be fixed by deletion.{1}"
                  .format(resource_name or self.full_name, valuable_msg))


    # API to handle copying properties from definition to state
    # after resource is created or updated and checking that
    # the state is out of sync with the definition
    def copy_properties(self, defn):
        for attr in self.defn_properties:
            setattr(self, attr, getattr(defn, attr))

    def properties_changed(self, defn):
        return any( getattr(self, attr) != getattr(defn, attr)
                    for attr in self.defn_properties )
