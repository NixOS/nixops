# -*- coding: utf-8 -*-

# Automatic provisioning of GSE Buckets

import os
import re
import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string, optional_int, optional_bool

class GSEResponse(libcloud.common.google.GoogleResponse):
    pass

class GSEConnection(libcloud.common.google.GoogleBaseConnection):
    """Connection class for the GSE"""
    host = 'www.googleapis.com'
    responseCls = GSEResponse

    def __init__(self, user_id, key, secure, **kwargs):
        self.scope = ['https://www.googleapis.com/auth/devstorage.read_write']
        super(GSEConnection, self).__init__(user_id, key, secure=secure,**kwargs)
        self.request_path = '/storage/v1/b'

    def _get_token_info_from_file(self):
      return None

    def _write_token_info_to_file(self):
      return


class GSEBucketDefinition(ResourceDefinition):
    """Definition of a GSE Bucket"""

    @classmethod
    def get_type(cls):
        return "gse-bucket"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.bucket_name = self.get_option_value(xml, 'name', str)

        self.cors = sorted( [ {
            'max_age_seconds': self.get_option_value(x, 'maxAgeSeconds', int, optional = True),
            'methods': self.get_option_value(x, 'methods', 'strlist'),
            'origins': self.get_option_value(x, 'origins', 'strlist'),
            'response_headers': self.get_option_value(x, 'responseHeaders', 'strlist')
          } for x in xml.find("attrs/attr[@name='cors']/list") ] )

        def parse_lifecycle(x):
            cond_x = x.find("attr[@name='conditions']")

            created_before = self.get_option_value(cond_x, 'createdBefore', str, optional = True)

            if created_before:
                m = re.match(r"^(\d*)-(\d*)-(\d*)$", created_before)
                if m:
                    normalized_created_before = "{0[0]:0>4}-{0[1]:0>2}-{0[2]:0>2}".format(m.groups())
                else:
                    raise Exception("createdBefore must be a date in 'YYYY-MM-DD' format")
            else:
                normalized_created_before = None

            return {
                'action': self.get_option_value(x, 'action', str),
                'age': self.get_option_value(cond_x, 'age', int, optional = True),
                'is_live':
                    self.get_option_value(cond_x, 'isLive', bool, optional = True),
                'created_before': normalized_created_before,
                'number_of_newer_versions':
                    self.get_option_value(cond_x, 'numberOfNewerVersions', int, optional = True)
            }
        self.lifecycle = sorted([ parse_lifecycle(x)
                           for x in xml.find("attrs/attr[@name='lifecycle']/list") ])

        if any( all(v is None for k,v in r.iteritems() if k != 'action')
                for r in self.lifecycle):
            raise Exception("Bucket '{0}' object lifecycle management "
                            "rule must specify at least one condition"
                            .format(self.bucket_name))

        logx = xml.find("attrs/attr[@name='logging']")
        self.copy_option(logx, 'logBucket', 'resource', optional = True)
        self.copy_option(logx, 'logObjectPrefix', str, optional = True)

        self.region = self.get_option_value(xml, 'location', str)
        self.copy_option(xml, 'storageClass', str)
        self.versioning_enabled = self.get_option_value(
                                      xml.find("attrs/attr[@name='versioning']"), 'enabled', bool)

        webx = xml.find("attrs/attr[@name='website']")
        self.website_main_page_suffix = self.get_option_value(webx, 'mainPageSuffix', str, optional = True)
        self.website_not_found_page = self.get_option_value(webx, 'notFoundPage', str, optional = True)


    def show_type(self):
        return "{0}".format(self.get_type())


class GSEBucketState(ResourceState):
    """State of a GSE Bucket"""

    bucket_name = attr_property("gce.name", None)

    cors = attr_property("gce.cors", [], 'json')
    lifecycle = attr_property("gce.lifecycle", [], 'json')
    log_bucket = attr_property("gce.logBucket", None)
    log_object_prefix = attr_property("gce.logObjectPrefix", None)
    region = attr_property("gce.region", None)
    storage_class = attr_property("gce.storageClass", None)
    versioning_enabled = attr_property("gce.versioningEnabled", None, bool)
    website_main_page_suffix = attr_property("gce.websiteMainPageSuffix", None)
    website_not_found_page = attr_property("gce.websiteNotFoundPage", None)

    @classmethod
    def get_type(cls):
        return "gse-bucket"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GSEBucketState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s


    @property
    def resource_id(self):
        return self.bucket_name

    nix_name = "gseBuckets"

    @property
    def full_name(self):
        return "GSE bucket '{0}'".format(self.bucket_name)

    def connect(self):
        if not self._conn:
            self._conn = GSEConnection(self.service_account, self.access_key_path, True)
        return self._conn

    defn_properties = [ 'cors', 'lifecycle', 'log_bucket', 'log_object_prefix',
                        'region', 'storage_class', 'versioning_enabled',
                        'website_main_page_suffix', 'website_not_found_page' ]

    def bucket_resource(self, defn):
        return {
            'name': defn.bucket_name,
            'cors': [ { 'origin': c['origins'],
                        'method': c['methods'],
                        'responseHeader': c['response_headers'],
                        'maxAgeSeconds': c['max_age_seconds']
                      } for c in defn.cors ],
            'lifecycle': {
                'rule': [ { 'action': { 'type': r['action'] },
                            'condition': {
                                'age': r['age'],
                                'isLive': r['is_live'],
                                'createdBefore': r['created_before'],
                                'numNewerVersions': r['number_of_newer_versions']
                            }
                        } for r in defn.lifecycle ]
            },
            'location': defn.region,
            'logging': {
                'logBucket': defn.log_bucket,
                'logObjectPrefix': defn.log_object_prefix
            } if defn.log_bucket is not None else {},
            'storageClass': defn.storage_class,
            'versioning': { 'enabled': defn.versioning_enabled },
            'website': {
                'mainPageSuffix': defn.website_main_page_suffix,
                'notFoundPage': defn.website_not_found_page
            }
        }

    def bucket(self):
        return self.connect().request("/{0}?projection=full".format(self.bucket_name), method = "GET").object

    def delete_bucket(self):
        return self.connect().request("/{0}".format(self.bucket_name), method = 'DELETE')

    def create_bucket(self, defn):
        return self.connect().request("?project={0}".format(self.project), method = 'POST',
                                      data = self.bucket_resource(defn))

    def update_bucket(self, defn):
        return self.connect().request("/{0}".format(self.bucket_name), method = 'PATCH',
                                      data = self.bucket_resource(defn))

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'storage_class')
        self.no_project_change(defn)
        self.no_region_change(defn)

        self.copy_credentials(defn)
        self.bucket_name = defn.bucket_name

        if check:
            try:
                b = self.bucket()
                if self.state == self.UP:

                    self.handle_changed_property('region', b['location'], can_fix = False)
                    self.handle_changed_property('storage_class', b['storageClass'], can_fix = False)

                    self.handle_changed_property('log_bucket',
                                                 b.get('logging', {}).get('logBucket', None))
                    self.handle_changed_property('log_object_prefix',
                                                 b.get('logging', {}).get('logObjectPrefix', None))
                    self.handle_changed_property('versioning_enabled',
                                                 b['versioning']['enabled'])
                    self.handle_changed_property('website_main_page_suffix',
                                                 b.get('website', {}).get('mainPageSuffix', None))
                    self.handle_changed_property('website_not_found_page',
                                                 b.get('website', {}).get('notFoundPage', None))

                    actual_cors = sorted( [ { 'origins': sorted(c.get('origin', [])),
                                              'methods': sorted(c.get('method', [])),
                                              'response_headers': sorted(c.get('responseHeader', [])),
                                              'max_age_seconds': int(c.get('maxAgeSeconds'))
                                          } for c in b.get('cors', {}) ] )
                    self.handle_changed_property('cors', actual_cors, property_name = 'CORS config')

                    actual_lifecycle = sorted( [ {
                                           'action': r.get('action', {}).get('type', None),
                                           'age': r.get('condition', {}).get('age', None),
                                           'is_live': r.get('condition', {}).get('isLive', None),
                                           'created_before': r.get('condition', {}).get('createdBefore', None),
                                           'number_of_newer_versions': r.get('condition', {}).get('numNewerVersions', None),
                                     } for r in b.get('lifecycle', {}).get('rule',[]) ] )
                    self.handle_changed_property('lifecycle', actual_lifecycle, property_name = 'lifecycle config')

                else:
                    self.warn_not_supposed_to_exist(valuable_resource = True, valuable_data = True)
                    if self.depl.logger.confirm("are you sure you want to destroy the existing {0}?".format(self.full_name)):
                        self.log("destroying...")
                        self.delete_bucket()
                    else: raise Exception("can't proceed further")

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log("creating {0}...".format(self.full_name))
            try:
                bucket = self.create_bucket(defn)
            except libcloud.common.google.GoogleBaseError as e:
                if e.value.get('message', None) == 'You already own this bucket. Please select another name.':
                    raise Exception("tried creating a GSE bucket that already exists; "
                                    "please run 'deploy --check' to fix this")
                else: raise
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating {0}...".format(self.full_name))
            self.update_bucket(defn)
            self.copy_properties(defn)

    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                bucket = self.bucket()
                if not self.depl.logger.confirm("are you sure you want to destroy {0}?".format(self.full_name)):
                    return False
                self.log("destroying {0}...".format(self.full_name))
                self.delete_bucket()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
        return True
