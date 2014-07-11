# -*- coding: utf-8 -*-

# Automatic provisioning of GSE Buckets

import os
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

        self.bucket_name = xml.find("attrs/attr[@name='name']/string").get("value")

        self.cors = sorted( [ {
            'max_age_seconds': optional_int(x.find("attr[@name='maxAgeSeconds']/int")),
            'methods': sorted([ m.get("value")
                            for m in x.findall("attr[@name='methods']/list/string")]),
            'origins': sorted([ o.get("value")
                            for o in x.findall("attr[@name='origins']/list/string")]),
            'response_headers': sorted([ rh.get("value")
                                     for rh in x.findall("attr[@name='responseHeaders']/list/string")])
          } for x in xml.findall("attrs/attr[@name='cors']/list/attrs") ] )

        def parse_lifecycle(x):
            cond_x = x.find("attr[@name='conditions']")

            return {
                'action': x.find("attr[@name='action']/string").get("value"),
                'age': optional_int(cond_x.find("attrs/attr[@name='age']/int")),
                'is_live': optional_bool(cond_x.find("attrs/attr[@name='isLive']/bool")),
                'created_before':
                    optional_string(cond_x.find("attrs/attr[@name='createdBefore']/string")),
                'number_of_newer_versions':
                    optional_int(cond_x.find("attrs/attr[@name='numberOfNewerVersions']/int"))
            }
        self.lifecycle = sorted([ parse_lifecycle(x)
                           for x in xml.findall("attrs/attr[@name='lifecycle']/list/attrs") ])

        if any(r['age'] is None and r['is_live'] is None and
               r['created_before'] is None and r['number_of_newer_versions'] is None
           for r in self.lifecycle):
            raise Exception("Bucket '{0}' object lifecycle management "
                            "rule must specify at least one condition"
                            .format(self.bucket_name))

        logx = xml.find("attrs/attr[@name='logging']")
        self.log_bucket =  ( optional_string(logx.find("attrs/attr[@name='logBucket']/string")) or
                            optional_string(logx.find("attrs/attr[@name='logBucket']/attrs/attr[@name='name']/string"))  )
        self.log_object_prefix = optional_string(logx.find("attrs/attr[@name='logObjectPrefix']/string"))

        self.region = xml.find("attrs/attr[@name='location']/string").get("value")
        self.storage_class = xml.find("attrs/attr[@name='storageClass']/string").get("value")
        self.versioning_enabled = xml.find("attrs/attr[@name='versioning']/"
                                           "attrs/attr[@name='enabled']/bool").get("value") == "true"

        webx = xml.find("attrs/attr[@name='website']")
        self.website_main_page_suffix = optional_string(webx.find("attrs/attr[@name='mainPageSuffix']/string"))
        self.website_not_found_page = optional_string(webx.find("attrs/attr[@name='notFoundPage']/string"))

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
        return "GSE Bucket '{0}'".format(self.bucket_name)

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
        self.no_change(self.storage_class != defn.storage_class, 'storage class')
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
                    if self.depl.logger.confirm("Are you sure you want to destroy the existing {0}?".format(self.full_name)):
                        self.log_start("Destroying...")
                        self.delete_bucket()
                        self.log_end("done.")
                    else: raise Exception("Can't proceed further.")

            except libcloud.common.google.ResourceNotFoundError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log_start("Creating {0}...".format(self.full_name))
            try:
                bucket = self.create_bucket(defn)
            except libcloud.common.google.GoogleBaseError as e:
                if e.value.get('message', None) == 'You already own this bucket. Please select another name.':
                    raise Exception("Tried creating a GSE Bucket that already exists. "
                                    "Please run 'deploy --check' to fix this.")
                else: raise

            self.log_end("done.")
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("Updating {0}...".format(self.full_name))
            self.update_bucket(defn)
            self.copy_properties(defn)

    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                bucket = self.bucket()
                if not self.depl.logger.confirm("Are you sure you want to destroy {0}?".format(self.full_name)):
                    return False
                self.log("Destroying {0}...".format(self.full_name))
                self.delete_bucket()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy {0} which didn't exist".format(self.full_name))
        return True
