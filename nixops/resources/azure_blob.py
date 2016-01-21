# -*- coding: utf-8 -*-

# Automatic provisioning of Azure BLOBs.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import StorageResourceDefinition, StorageResourceState

import hashlib
import base64

from nixops.resources.azure_blob_container import AzureBLOBContainerState
from nixops.resources.azure_storage import AzureStorageState


def md5sum(filename):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096 * md5.block_size), b''):
            md5.update(chunk)
    return base64.b64encode(md5.digest())

class AzureBLOBDefinition(StorageResourceDefinition):
    """Definition of an Azure BLOB"""

    @classmethod
    def get_type(cls):
        return "azure-blob"

    @classmethod
    def get_resource_type(cls):
        return "azureBlobs"

    def __init__(self, xml):
        StorageResourceDefinition.__init__(self, xml)

        self.blob_name = self.get_option_value(xml, 'name', str)

        self.copy_option(xml, 'blobType', str)
        if self.blob_type not in [ 'BlockBlob', 'PageBlob' ]:
            raise Exception('BLOB type must be either "PageBlob" or "BlockBlob"')

        self.copy_option(xml, 'filePath', str, optional = True)
        self.copy_option(xml, 'copyFromBlob', str, optional = True)
        if self.file_path and self.copy_from_blob:
            raise Exception('Must specify either filePath or copyFromBlob, but not both')
        if not self.file_path and not self.copy_from_blob:
            raise Exception('Must specify either filePath or copyFromBlob')

        self.copy_option(xml, 'container', 'resource')
        self.copy_option(xml, 'storage', 'resource', optional = True)
        self.copy_option(xml, 'contentEncoding', str, optional = True)
        self.copy_option(xml, 'contentLanguage', str, optional = True)
        self.copy_option(xml, 'contentType', str, optional = True)
        self.copy_option(xml, 'contentLength', int, optional = True)
        self.copy_option(xml, 'cacheControl', str, optional = True)
        self.copy_option(xml, 'contentDisposition', str, optional = True)
        self.copy_metadata(xml)

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureBLOBState(StorageResourceState):
    """State of an Azure BLOB"""

    blob_name = attr_property("azure.name", None)
    blob_type = attr_property("azure.blobType", None)
    md5 = attr_property("azure.md5", None)
    container = attr_property("azure.container", None)
    storage = attr_property("azure.storage", None)
    content_encoding = attr_property("azure.contentEncoding", None)
    content_language = attr_property("azure.contentLanguage", None)
    content_type = attr_property("azure.contentType", None)
    content_length = attr_property("azure.contentLength", None)
    cache_control = attr_property("azure.cacheControl", None)
    content_disposition = attr_property("azure.contentDisposition", None)
    metadata = attr_property("azure.metadata", {}, 'json')
    last_modified = attr_property("azure.lastModified", None)
    copied_from = attr_property("azure.copiedFrom", None)

    @classmethod
    def get_type(cls):
        return "azure-blob"

    def show_type(self):
        s = super(AzureBLOBState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.blob_name

    @property
    def full_name(self):
        return "Azure BLOB '{0}'".format(self.resource_id)

    def get_storage_name(self, defn = None):
        container_resource = self.get_resource_state(AzureBLOBContainerState, (defn or self).container)
        return (defn or self).storage or (container_resource and container_resource.storage)

    def get_key(self):
        storage = self.get_resource_state(AzureStorageState, self.storage)
        container = self.get_resource_state(AzureBLOBContainerState, self.container)
        access_key = self.access_key or (storage and storage.access_key) or (container and container.get_key())

        if not access_key:
            raise Exception("Can't obtain the access key needed to manage {0}"
                            .format(self.full_name))
        return access_key

    def is_settled(self, resource):
        return resource is None or (resource.get('x-ms-copy-status', 'success') == 'success')

    def get_resource_allow_exceptions(self):
        return self.bs().get_blob_properties(self.container, self.resource_id)

    def destroy_resource(self):
        self.bs().delete_blob(self.container, self.resource_id,
                              x_ms_delete_snapshots = 'include' )
        self.copied_from = None
        self.last_modified = None
        self.state = self.MISSING

    defn_properties = [ 'content_encoding', 'content_language',
                        'cache_control', 'content_type', 'content_disposition' ]

    def upload_file(self, defn):
        md5 = md5sum(defn.file_path)

        if self.state != self.UP or md5 != self.md5 or self.blob_type != defn.blob_type:
            blob = self.get_settled_resource()

            if self.state == self.UP:
                self.log("updating the contents of {0} in {1}...".format(self.full_name, defn.container))
                if blob is not None and self.blob_type != defn.blob_type:
                    self.log("blob type change requested; deleting the destination BLOB first...")
                    self.destroy_resource()
            else:
                self.log("creating {0} in {1}...".format(self.full_name, defn.container))

            if defn.blob_type == 'BlockBlob':
                self.bs().put_block_blob_from_path(
                                  defn.container, defn.blob_name, defn.file_path,
                                  content_encoding = defn.content_encoding,
                                  content_language = defn.content_language,
                                  content_md5 = md5,
                                  cache_control = defn.cache_control,
                                  x_ms_blob_content_type = defn.content_type,
                                  x_ms_blob_content_encoding = defn.content_encoding,
                                  x_ms_blob_content_language = defn.content_language,
                                  x_ms_blob_content_md5 = md5,
                                  x_ms_blob_cache_control = defn.cache_control,
                                  x_ms_meta_name_values = defn.metadata,
                                  max_connections = 8)
            else:
                self.bs().put_page_blob_from_path(
                                        defn.container, defn.blob_name, defn.file_path,
                                        content_encoding = defn.content_encoding,
                                        content_language = defn.content_language,
                                        content_md5 = md5,
                                        cache_control = defn.cache_control,
                                        x_ms_blob_content_type = defn.content_type,
                                        x_ms_blob_content_encoding = defn.content_encoding,
                                        x_ms_blob_content_language = defn.content_language,
                                        x_ms_blob_content_md5 = md5,
                                        x_ms_blob_cache_control = defn.cache_control,
                                        x_ms_meta_name_values = defn.metadata,
                                        max_connections = 8)
            self.state = self.UP
            self.copy_properties(defn)
            self.metadata = defn.metadata
            self.blob_type = defn.blob_type
            self.md5 = md5
            self.last_modified = None
            self.content_disposition = None
            self.copied_from = defn.file_path
            self.content_length = defn.content_length or os.stat(defn.file_path).st_size


    def copy_blob(self, defn):
        if self.state == self.UP:
            self.log("updating the contents of {0} in {1}..."
                     .format(self.full_name, defn.container))
            if self.copied_from != defn.copy_from_blob:
                self.log("source BLOB location has changed; deleting {0} first.."
                         .format(self.full_name))
                self.destroy_resource()
            elif self.blob_type != defn.blob_type:
                self.warn("when copying, cannot change the BLOB type from {0} to {1}"
                         .format(self.blob_type, defn.blob_type))
        else:
            self.log("creating {0} in {1}...".format(self.full_name, defn.container))
            self.last_modified = None
        try:
            self.bs().copy_blob(defn.container, defn.blob_name, defn.copy_from_blob,
                                x_ms_meta_name_values = defn.metadata,
                                x_ms_source_if_modified_since = self.last_modified)
            res = self.get_settled_resource(max_tries=600)
            self.copy_properties(defn)
            self.last_modified = res.get('last-modified', None)
            self.copied_from = defn.copy_from_blob
            self.md5 = res.get('content-md5', None)
            self.content_encoding = res.get('content-encoding', None)
            self.content_language = res.get('content-language', None)
            self.content_length = res.get('content-length', None)
            self.content_type = res.get('content-type', None)
            self.cache_control =  res.get('cache-control', None)
            self.blob_type = res.get('x-ms-blob-type', None)
            self.content_disposition = res.get('content-disposition', None)
            # workaround for API bug
            self.metadata = None if defn.metadata == {} else defn.metadata 
            self.state = self.UP
            if self.blob_type != defn.blob_type:
                self.warn("cannot change blob type when copying; "
                          "BLOB of type {0} has been created instead "
                          "of the requested {1}"
                          .format(self.blob_type, defn.blob_type))
        except azure.common.AzureHttpError as e:
          if e.status_code == 304 or e.status_code == 412:
              self.log("update is not necessary, the source BLOB has not been modified")
          else:
              raise


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(self.get_storage_name(defn=self) !=
                       self.get_storage_name(defn=defn), 'storage')
        self.no_property_change(defn, 'container')

        self.blob_name = defn.blob_name
        self.access_key = defn.access_key
        self.storage = defn.storage
        self.container = defn.container

        if check:
            blob = self.get_settled_resource()
            if not blob:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('blob_type', blob.get('x-ms-blob-type', None))
                self.handle_changed_property('md5', blob.get('content-md5', None))
                self.handle_changed_property('content_encoding', blob.get('content-encoding', None))
                self.handle_changed_property('content_language', blob.get('content-language', None))
                self.handle_changed_property('content_length', blob.get('content-length', None), can_fix = False)
                self.handle_changed_property('content_type', blob.get('content-type', None))
                self.handle_changed_property('cache_control', blob.get('cache-control', None))
                self.handle_changed_property('content_disposition', blob.get('content-disposition', None))
                self.handle_changed_metadata(blob)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if defn.file_path:
            self.upload_file(defn)
        if defn.copy_from_blob:
            self.copy_blob(defn)

        if self.properties_changed(defn) or self.metadata != defn.metadata:
            self.log("updating properties of {0}...".format(self.full_name))
            self.get_settled_resource_assert_exists()
            self.bs().set_blob_properties(self.container, self.blob_name,
                                          x_ms_blob_cache_control = defn.cache_control,
                                          x_ms_blob_content_type  = defn.content_type,
                                          x_ms_blob_content_md5 = self.md5,
                                          x_ms_blob_content_encoding = defn.content_encoding,
                                          x_ms_blob_content_language = defn.content_language,
                                          x_ms_blob_content_disposition = defn.content_disposition)
            self.copy_properties(defn)
            self.bs().set_blob_metadata(self.container, self.blob_name,
                                             x_ms_meta_name_values = defn.metadata)
            self.metadata = defn.metadata


    def create_after(self, resources, defn):
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState)}
