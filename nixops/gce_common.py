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

    def credentials_prefix(self):
        return "resources.{0}.$NAME".format(self.nix_name())

    def defn_project(self, defn):
        project = defn.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘{0}.project’ or $GCE_PROJECT".format(self.credentials_prefix()))
        return project

    def defn_service_account(self, defn):
        service_account = defn.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘{0}.serviceAccount’ or $GCE_SERVICE_ACCOUNT".format(self.credentials_prefix()))
        return service_account

    def defn_access_key_path(self, defn):
        access_key_path = defn.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘{0}.accessKey’ or $ACCESS_KEY_PATH".format(self.credentials_prefix()))
        return access_key_path

    def copy_credentials(self, defn):
        self.project = self.defn_project(defn)
        self.service_account = self.defn_service_account(defn)
        self.access_key_path = self.defn_access_key_path(defn)
