# -*- coding: utf-8 -*-

# Automatic provisioning of Azure Files.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import StorageResourceDefinition, StorageResourceState

import hashlib
import base64

from nixops.resources.azure_directory import AzureDirectoryState
from nixops.resources.azure_share import AzureShareState
from nixops.resources.azure_storage import AzureStorageState

def md5sum(filename):
    md5 = hashlib.md5()
    with open(filename, 'rb') as f:
        for chunk in iter(lambda: f.read(4096 * md5.block_size), b''):
            md5.update(chunk)
    return base64.b64encode(md5.digest())

class AzureFileDefinition(StorageResourceDefinition):
    """Definition of an Azure File"""

    @classmethod
    def get_type(cls):
        return "azure-file"

    @classmethod
    def get_resource_type(cls):
        return "azureFiles"

    def __init__(self, xml):
        StorageResourceDefinition.__init__(self, xml)

        self.file_name = self.get_option_value(xml, 'name', str)

        self.copy_option(xml, 'filePath', str)

        self.copy_option(xml, 'share', 'resource', optional = True)
        self.copy_option(xml, 'directoryPath', str, optional = True)
        self.copy_option(xml, 'directory', 'resource', optional = True)
        if not(self.share or self.directory):
            raise Exception("{0}: must specify at least directory or share"
                            .format(self.file_name))
        if self.directory_path and not self.share:
            raise Exception("{0}: if you specify directoryPath, you must also specify share"
                            .format(self.file_name))
        if self.directory_path and self.directory:
            raise Exception("{0}: can't specify directory and directoryPath at once"
                            .format(self.file_name))

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


class AzureFileState(StorageResourceState):
    """State of an Azure File"""

    file_name = attr_property("azure.name", None)
    md5 = attr_property("azure.md5", None)
    share = attr_property("azure.share", None)
    directory = attr_property("azure.directory", None)
    directory_path = attr_property("azure.directoryPath", None)
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
        return "azure-file"

    def show_type(self):
        s = super(AzureFileState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.file_name

    nix_name = "azureFiles"

    @property
    def full_name(self):
        return "Azure file '{0}'".format(self.resource_id)

    def get_storage_name(self, defn = None):
        parent_resource = self.get_resource_state(AzureDirectoryState, (defn or self).directory)
        share_resource = self.get_resource_state(AzureShareState, (defn or self).share)
        return( (defn or self).storage or
                (share_resource and share_resource.get_storage_name()) or
                (parent_resource and parent_resource.get_storage_name()) )

    def get_key(self):
        parent = self.get_resource_state(AzureDirectoryState, self.directory)
        storage = self.get_resource_state(AzureStorageState, self.get_storage_name())
        share = self.get_resource_state(AzureShareState, self.share)
        access_key = ( self.access_key or
                      (storage and storage.access_key) or
                      (share and share.get_key()) or
                      (parent and parent.get_key()) )

        if not access_key:
            raise Exception("Can't obtain the access key needed to manage {0}"
                            .format(self.full_name))
        return access_key

    def is_settled(self, resource):
        return resource is None or (resource.get('x-ms-copy-status', 'success') == 'success')


    def get_share_name(self, defn = None):
        parent = self.get_resource_state(AzureDirectoryState, (defn or self).directory)
        return( (defn or self).share or
                (parent and parent.get_share_name()) )

    def get_directory_path(self, defn = None):
        directory = self.get_resource_state(AzureDirectoryState, (defn or self).directory)
        return self.directory_path or (directory and directory.get_directory_path())

    def get_resource_allow_exceptions(self):
        return self.fs().get_file_properties(self.get_share_name(), self.get_directory_path(), self.resource_id)

    def destroy_resource(self):
        self.fs().delete_file(self.get_share_name(), self.get_directory_path(), self.resource_id)
        self.copied_from = None
        self.last_modified = None
        self.state = self.MISSING

    defn_properties = [ 'content_encoding', 'content_language', 'metadata',
                        'cache_control', 'content_type', 'content_disposition' ]

    def _upload_file(self, defn):
        md5 = md5sum(defn.file_path)

        if self.state != self.UP or md5 != self.md5:
            self.get_settled_resource()

            if self.state == self.UP:
                self.log("updating the contents of {0} in {1}/{2}..."
                         .format(self.full_name, self.get_share_name(),
                                 self.get_directory_path()))
            else:
                self.log("creating {0} in {1}/{2}..."
                         .format(self.full_name, self.get_share_name(),
                                 self.get_directory_path()))

            self.fs().put_file_from_path(
                              self.get_share_name(), self.get_directory_path(), defn.file_name,
                              defn.file_path,
                              x_ms_content_type = defn.content_type,
                              x_ms_content_encoding = defn.content_encoding,
                              x_ms_content_language = defn.content_language,
                              x_ms_content_md5 = md5,
                              x_ms_cache_control = defn.cache_control,
                              x_ms_meta_name_values = defn.metadata,
                              max_connections = 8)
            self.state = self.UP
            self.copy_properties(defn)
            self.md5 = md5
            self.last_modified = None
            # a workaround the bindings bug, force metadata update
            self.content_disposition = "METADATA NEEDS AN UPDATE"
            self.copied_from = defn.file_path
            self.content_length = defn.content_length or os.stat(defn.file_path).st_size


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(self.get_storage_name(defn=self) !=
                       self.get_storage_name(defn=defn), 'storage')
        self.no_change(self.get_share_name(defn=self) !=
                       self.get_share_name(defn=defn), 'share')
        self.no_change(self.get_directory_path(defn=self) !=
                       self.get_directory_path(defn=defn), 'directory path')

        self.file_name = defn.file_name
        self.access_key = defn.access_key
        self.storage = defn.storage
        self.share = defn.share
        self.directory = defn.directory
        self.directory_path = defn.directory_path

        if check:
            file = self.get_settled_resource()
            if not file:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('md5', file.get('content-md5', None))
                self.handle_changed_property('content_encoding', file.get('content-encoding', None))
                self.handle_changed_property('content_language', file.get('content-language', None))
                self.handle_changed_property('content_length', file.get('content-length', None), can_fix = False)
                self.handle_changed_property('content_type', file.get('content-type', None))
                self.handle_changed_property('cache_control', file.get('cache-control', None))
                self.handle_changed_property('content_disposition', file.get('content-disposition', None))
                self.handle_changed_metadata(file)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        self._upload_file(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self.fs().set_file_metadata(self.get_share_name(), self.get_directory_path(), self.file_name,
                                        x_ms_meta_name_values = defn.metadata)
            self.metadata = defn.metadata
            self.fs().set_file_properties(self.get_share_name(), self.get_directory_path(), self.file_name,
                                          x_ms_cache_control = defn.cache_control,
                                          x_ms_content_type  = defn.content_type,
                                          x_ms_content_md5 = self.md5,
                                          x_ms_content_encoding = defn.content_encoding,
                                          x_ms_content_language = defn.content_language,
                                          x_ms_content_disposition = defn.content_disposition)
            self.copy_properties(defn)


    def create_after(self, resources, defn):
        return {r for r in resources
                  if isinstance(r, AzureShareState) or isinstance(r, AzureStorageState) or
                     isinstance(r, AzureDirectoryState)}
