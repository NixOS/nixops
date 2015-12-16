# -*- coding: utf-8 -*-

# Automatic provisioning of Azure OS images.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState


class AzureOSImageDefinition(ResourceDefinition):
    """Definition of an Azure OS Image"""

    @classmethod
    def get_type(cls):
        return "azure-os-image"

    @classmethod
    def get_resource_type(cls):
        return "azureOSImages"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.os_image_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'label', str, empty = False)
        self.copy_option(xml, 'mediaLink', str, empty = False)
        self.copy_option(xml, 'os', str, optional = True)
        if self.os not in ["Linux", "Windows"]:
            raise Exception("OS Image {0} OS must be Linux or Windows"
                            .format(self.os_image_name))

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.os)


class AzureOSImageState(ResourceState):
    """State of an Azure OS Image"""

    os_image_name = attr_property("azure.name", None)
    label = attr_property("azure.label", None)
    os = attr_property("azure.os", None)
    media_link = attr_property("azure.mediaLink", None)

    @classmethod
    def get_type(cls):
        return "azure-os-image"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.os)

    @property
    def resource_id(self):
        return self.os_image_name

    nix_name = "azureOSImages"

    @property
    def full_name(self):
        return "Azure OS image '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.sms().get_os_image(self.resource_id)
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        req = self.sms().delete_os_image(self.resource_id)
        self.finish_request(req)

    def is_settled(self, resource):
        return True


    defn_properties = [ 'label', 'media_link', 'os' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        # media_link change requests fail silently
        self.no_property_change(defn, 'media_link')

        self.copy_credentials(defn)
        self.os_image_name = defn.os_image_name

        if check:
            image = self.get_settled_resource()
            if not image:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('media_link', image.media_link)
                self.handle_changed_property('label', image.label)
                self.handle_changed_property('os', image.os)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating an OS image that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} using {1}...".format(self.full_name, defn.media_link))
            req = self.sms().add_os_image(defn.label, defn.media_link,
                                          defn.os_image_name, defn.os)
            self.finish_request(req)
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            req = self.sms().update_os_image(self.os_image_name, defn.label, defn.media_link,
                                             defn.os_image_name, defn.os)
            self.finish_request(req)
            self.copy_properties(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_blob import AzureBLOBState
        from nixops.resources.azure_blob_container import AzureBLOBContainerState
        from nixops.resources.azure_storage import AzureStorageState
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState) or
                     isinstance(r, AzureBLOBState)}
