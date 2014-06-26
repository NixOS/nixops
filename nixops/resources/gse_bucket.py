# -*- coding: utf-8 -*-

# Automatic provisioning of GSE Buckets

import os
import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState, optional_string

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

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class GSEBucketState(ResourceState):
    """State of a GSE Bucket"""

    bucket_name = attr_property("gce.name", None)

    @classmethod
    def get_type(cls):
        return "gse-bucket"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(GSEBucketState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s


    @property
    def resource_id(self):
        return self.bucket_name

    def nix_name(self):
        return "gseBuckets"

    def connect(self):
        if self._conn: return self._conn

        service_account = self.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘resources.{0}.$NAME.serviceAccount’ or $GCE_SERVICE_ACCOUNT".format(self.nix_name()))

        access_key_path = self.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘resources.{0}.$NAME.accessKey’ or $ACCESS_KEY_PATH".format(self.nix_name()))

        project = self.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘resources.{0}.$NAME.project’ or $GCE_PROJECT".format(self.nix_name()))

        self._conn = GSEConnection(service_account, access_key_path, True)
        return self._conn

    def bucket(self):
        return self.connect().request("/{0}".format(self.bucket_name), method = "GET")

    def delete_bucket(self):
        return self.connect().request("/{0}".format(self.bucket_name), method = 'DELETE')

    def create_bucket(self, bname):
        return self.connect().request("?project={0}".format(self.project), method = 'POST', data = {
            'name': bname
          })

    def create(self, defn, check, allow_reboot, allow_recreate):
        if self.state == self.UP:
            if self.project != defn.project:
                raise Exception("cannot change the project of a deployed GSE Bucket")

        self.copy_credentials(defn)
        self.bucket_name = defn.bucket_name

        if check:
            try:
                bucket = self.bucket()
                if self.state == self.UP:
                    # FIXME: check state
                    self.log('OK')
                else:
                    self.warn("GSE Bucket ‘{0}’ exists, but isn't supposed to. Probably, this is the result "
                              "of a botched creation attempt and can be fixed by deletion. However, this also "
                              "could be a resource name collision, and valuable data could be lost. "
                              "Before proceeding, please ensure that the bucket doesn't contain useful data."
                              .format(defn.bucket_name))
                    if self.depl.logger.confirm("Are you sure you want to destroy the existing bucket ‘{0}’?".format(defn.bucket_name)):
                        self.log_start("Destroying...")
                        self.delete_bucket()
                        self.log_end("done.")
                    else: raise Exception("Can't proceed further.")

            except libcloud.common.google.ResourceNotFoundError:
                if self.state == self.UP:
                    self.warn("GSE Bucket ‘{0}’ is supposed to exist, but is missing. Recreating...".format(defn.bucket_name))
                    self.state = self.MISSING

        if self.state != self.UP:
            self.log_start("Creating GSE Bucket ‘{0}’...".format(defn.bucket_name))
            try:
                bucket = self.create_bucket(defn.bucket_name)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating a GSE Bucket that already exists. Please run ‘deploy --check’ to fix this.")

            self.log_end("done.")
            self.state = self.UP


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                bucket = self.bucket()
                if not self.depl.logger.confirm("Are you sure you want to destroy GSE Bucket ‘{0}’?".format(self.bucket_name)):
                    return False
                self.log("Destroying GSE Bucket ‘{0}’...".format(self.bucket_name))
                self.delete_bucket()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("Tried to destroy GSE Bucket ‘{0}’ which didn't exist".format(self.bucket_name))
        return True
