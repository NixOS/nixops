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

def ensure_not_empty(value, name):
    if not value:
        raise Exception("{0} must not be empty".format(name))

def ensure_positive(value, name):
    if value <= 0:
        raise Exception("{0} must be a positive integer".format(name))

class ResourceDefinition(nixops.resources.ResourceDefinition):

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)

        res_name = xml.find("attrs/attr[@name='name']/string").get("value")
        if len(res_name)>63 or re.match('[a-z]([-a-z0-9]{0,61}[a-z0-9])?$', res_name) is None:
            raise Exception("Resource name ‘{0}‘ must be 1-63 characters long and "
              "match the regular expression [a-z]([-a-z0-9]*[a-z0-9])? which "
              "means the first character must be a lowercase letter, and all "
              "following characters must be a dash, lowercase letter, or digit, "
              "except the last character, which cannot be a dash.".format(res_name))

        self.project = xml.find("attrs/attr[@name='project']/string").get("value")
        self.service_account = xml.find("attrs/attr[@name='serviceAccount']/string").get("value")
        self.access_key_path = xml.find("attrs/attr[@name='accessKey']/string").get("value")


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

    def no_project_change(self, defn):
        if self.state == self.UP:
            if self.project != self.defn_project(defn):
                raise Exception("Cannot change the project of a deployed {0}".format(self.full_name))

    def no_region_change(self, defn):
        if self.state == self.UP:
            if self.region != defn.region:
                raise Exception("Cannot change the region of a deployed {0}".format(self.full_name))

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
