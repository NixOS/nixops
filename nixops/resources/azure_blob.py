# -*- coding: utf-8 -*-

# Automatic provisioning of Azure BLOBs.

import os
import azure
from azure.storage.blob import BlobService

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState

import hashlib
import base64

def md5sum(filename):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096 * md5.block_size), b''):
            md5.update(chunk)
    return base64.b64encode(md5.digest())

class AzureBLOBDefinition(ResourceDefinition):
    """Definition of an Azure BLOB"""

    @classmethod
    def get_type(cls):
        return "azure-blob"

    @classmethod
    def get_resource_type(cls):
        return "azureBlobs"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.blob_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'accessKey', str, optional = True)
        self.copy_option(xml, 'blobType', str)
        self.copy_option(xml, 'filePath', str)
        if self.blob_type not in [ 'block', 'page' ]:
            raise Exception('BLOB type must be either "page" or "block"')
        self.copy_option(xml, 'container', 'resource')
        self.copy_option(xml, 'storage', 'resource', optional = True)
        self.copy_option(xml, 'contentEncoding', str, optional = True)
        self.copy_option(xml, 'contentLanguage', str, optional = True)
        self.copy_option(xml, 'contentType', str, optional = True)
        self.copy_option(xml, 'contentLength', int, optional = True)
        self.copy_option(xml, 'cacheControl', str, optional = True)
        self.metadata = {
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='metadata']/attrs/attr")
        }

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureBLOBState(ResourceState):
    """State of an Azure BLOB"""

    blob_name = attr_property("azure.name", None)
    blob_type = attr_property("azure.blobType", None)
    md5 = attr_property("azure.md5", None)
    access_key = attr_property("azure.accessKey", None)
    container = attr_property("azure.container", None)
    storage = attr_property("azure.storage", None)
    content_encoding = attr_property("azure.contentEncoding", None)
    content_language = attr_property("azure.contentLanguage", None)
    content_type = attr_property("azure.contentType", None)
    content_length = attr_property("azure.contentLength", None)
    cache_control = attr_property("azure.cacheControl", None)
    metadata = attr_property("azure.metadata", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-blob"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)
        self._bs = None

    def show_type(self):
        s = super(AzureBLOBState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.blob_name

    nix_name = "azureBlobs"

    @property
    def full_name(self):
        return "Azure BLOB '{0}'".format(self.resource_id)

    def get_container_resource(self):
        return next((r for r in self.depl.resources.values()
                       if getattr(r, 'container_name', None) == self.container), None)

    def get_key(self):
        storage = self.storage and next((r for r in self.depl.resources.values()
                                           if getattr(r, 'storage_name', None) == self.storage), None)
        container = self.get_container_resource()
        access_key = self.access_key or (storage and storage.access_key) or (container and container.get_key())

        if not access_key:
            raise Exception("Can't obtain the access key needed to manage {0}"
                            .format(self.full_name))
        return access_key

    def bs(self):
        if not self._bs:
            container_resource = self.get_container_resource()
            self._bs = BlobService(self.storage or (container_resource and container_resource.storage),
                                   self.get_key())
        return self._bs

    def is_settled(self, resource):
        return True

    def get_resource(self):
        try:
            return self.bs().get_blob_properties(self.container, self.resource_id)
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.bs().delete_blob(self.container, self.resource_id,
                              x_ms_delete_snapshots = 'include' )

    defn_properties = [ 'blob_type', 'content_encoding', 'content_language',
                        'cache_control', 'content_type' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'storage')
        self.no_property_change(defn, 'container')
        self.no_property_change(defn, 'blob_type')

        self.copy_credentials(defn)
        self.blob_name = defn.blob_name
        self.access_key = defn.access_key
        self.storage = defn.storage
        self.container = defn.container

        if check:
            blob = self.get_settled_resource()
            if not blob:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.warn_if_changed({'block':'BlockBlob', 'page':'PageBlob'}[self.blob_type],
                                       blob.get('x-ms-blob-type', None),
                                      'blob type', can_fix = False)
                self.handle_changed_property('md5', blob.get('content-md5', None))
                self.handle_changed_property('content_encoding', blob.get('content-encoding', None))
                self.handle_changed_property('content_language', blob.get('content-language', None))
                self.handle_changed_property('content_length', blob.get('content-length', None), can_fix = False)
                self.handle_changed_property('content_type', blob.get('content-type', None))
                self.handle_changed_property('cache_control', blob.get('cache-control', None))
                metadata = { k[10:] : v
                             for k, v in blob.items()
                             if k.startswith('x-ms-meta-') }
                self.handle_changed_property('metadata', metadata)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        md5 = md5sum(defn.file_path)

        if self.state != self.UP or md5 != self.md5:
            self.get_settled_resource()

            if self.state == self.UP:
                self.log("updating the contents of {0} in {1}...".format(self.full_name, defn.container))
            else:
                self.log("creating {0} in {1}...".format(self.full_name, defn.container))

            if defn.blob_type == 'block':
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
            self.md5 = md5
            self.content_length = defn.content_length or os.stat(defn.file_path).st_size

        if self.properties_changed(defn) or self.metadata != defn.metadata:
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self.bs().set_blob_properties(self.container, self.blob_name,
                                          x_ms_blob_cache_control = defn.cache_control,
                                          x_ms_blob_content_type  = defn.content_type,
                                          x_ms_blob_content_md5 = md5,
                                          x_ms_blob_content_encoding = defn.content_encoding,
                                          x_ms_blob_content_language = defn.content_language)
            self.copy_properties(defn)
            self.bs().set_blob_metadata(self.container, self.blob_name,
                                             x_ms_meta_name_values = defn.metadata)
            self.metadata = defn.metadata



    def create_after(self, resources, defn):
        from nixops.resources.azure_blob_container import AzureBLOBContainerState
        from nixops.resources.azure_storage import AzureStorageState
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState)}
