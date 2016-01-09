# -*- coding: utf-8 -*-

# Automatic provisioning of Azure Directories.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import StorageResourceDefinition, StorageResourceState

from nixops.resources.azure_share import AzureShareState
from nixops.resources.azure_storage import AzureStorageState

class AzureDirectoryDefinition(StorageResourceDefinition):
    """Definition of an Azure Directory"""

    @classmethod
    def get_type(cls):
        return "azure-directory"

    @classmethod
    def get_resource_type(cls):
        return "azureDirectories"

    def __init__(self, xml):
        StorageResourceDefinition.__init__(self, xml)

        self.directory_name = self.get_option_value(xml, 'name', str)

        self.copy_option(xml, 'parentDirectoryPath', str, optional = True)
        self.copy_option(xml, 'parentDirectory', 'resource', optional = True)
        self.copy_option(xml, 'share', 'resource', optional = True)
        self.copy_option(xml, 'storage', 'resource', optional = True)
        if not(self.share or self.parent_directory):
            raise Exception("{0}: must specify at least parentDirectory or share"
                            .format(self.directory_name))
        if self.parent_directory_path and not self.share:
            raise Exception("{0}: if you specify parentDirectoryPath, you must also specify share"
                            .format(self.directory_name))
        if self.parent_directory_path and self.parent_directory:
            raise Exception("{0}: can't specify parentDirectory and parentDirectoryPath at once"
                            .format(self.directory_name))

    def show_type(self):
        return "{0}".format(self.get_type())


class AzureDirectoryState(StorageResourceState):
    """State of an Azure Directory"""

    directory_name = attr_property("azure.name", None)
    parent_directory_path = attr_property("azure.parentDirectoryPath", None)
    parent_directory = attr_property("azure.parentDirectory", None)
    share = attr_property("azure.share", None)
    storage = attr_property("azure.storage", None)

    @classmethod
    def get_type(cls):
        return "azure-directory"

    def show_type(self):
        s = super(AzureDirectoryState, self).show_type()
        if self.state == self.UP: s = "{0}".format(s)
        return s

    @property
    def resource_id(self):
        return self.directory_name

    nix_name = "azureDirectories"

    @property
    def full_name(self):
        return "Azure directory '{0}'".format(self.resource_id)

    def get_share_name(self, defn = None):
        parent_resource = self.get_resource_state(AzureDirectoryState, (defn or self).parent_directory)
        return( (defn or self).share or
                (parent_resource and parent_resource.get_share_name()) )

    def get_storage_name(self, defn = None):
        parent_resource = self.get_resource_state(AzureDirectoryState, (defn or self).parent_directory)
        share_resource = self.get_resource_state(AzureShareState, (defn or self).share)
        return( (defn or self).storage or
                (share_resource and share_resource.get_storage_name()) or
                (parent_resource and parent_resource.get_storage_name()) )

    def get_key(self):
        parent = self.get_resource_state(AzureDirectoryState, self.parent_directory)
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
        return True

    def get_parent_directory_path(self, defn = None):
        parent = self.get_resource_state(AzureDirectoryState, (defn or self).parent_directory)
        return (defn or self).parent_directory_path or (parent and parent.get_directory_path())

    def get_directory_path(self):
        parent = self.get_parent_directory_path()
        return "{0}/{1}".format(parent, self.directory_name) if parent else self.directory_name

    def get_resource_allow_exceptions(self):
        return self.fs().get_directory_properties(self.get_share_name(), self.get_directory_path())

    def destroy_resource(self):
        self.fs().delete_directory(self.get_share_name(), self.get_directory_path(), fail_not_exist = True)


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(self.get_storage_name(defn=self) !=
                       self.get_storage_name(defn=defn), 'storage')
        self.no_change(self.get_share_name(defn=self) !=
                       self.get_share_name(defn=defn), 'share')
        self.no_change(self.get_parent_directory_path(defn=self) !=
                       self.get_parent_directory_path(defn=defn), 'parent directory path')

        self.directory_name = defn.directory_name
        self.access_key = defn.access_key
        self.storage = defn.storage
        self.share = defn.share
        self.parent_directory = defn.parent_directory
        self.parent_directory_path = defn.parent_directory_path

        if check:
            directory = self.get_settled_resource()
            if not directory:
                self.warn_missing_resource()
            elif self.state == self.UP:
                # bindings as of 05.01.2016 don't allow getting/setting metadata
                self.is_settled(directory) # placeholder
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource() is not None:
                raise Exception("tried creating a directory that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.directory_name,
                                                     self.get_storage_name()))
            self.fs().create_directory(self.get_share_name(),
                                       self.get_directory_path(),
                                       fail_on_exist = True)
            self.state = self.UP


    def create_after(self, resources, defn):
        return { r for r in resources
                   if isinstance(r, AzureShareState) or isinstance(r, AzureStorageState) or
                     (isinstance(r, AzureDirectoryState) and defn.parent_directory and 
                         (getattr(self.depl.definitions[r.name], 'directory_name', None)
                              == defn.parent_directory) )
               }

    def destroy_before(self, resources):
        return {r for r in resources
                  if isinstance(r, AzureShareState) or isinstance(r, AzureStorageState) 
                  or
                     (isinstance(r, AzureDirectoryState) and self.parent_directory and
                      getattr(r, 'directory_name', None) == self.parent_directory )
                     }
