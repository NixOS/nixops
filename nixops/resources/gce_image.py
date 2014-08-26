# -*- coding: utf-8 -*-

# Automatic provisioning of GCE Images.

import os
import libcloud.common.google

from nixops.util import attr_property
from nixops.gce_common import ResourceDefinition, ResourceState


class GCEImageDefinition(ResourceDefinition):
    """Definition of a GCE Image"""

    @classmethod
    def get_type(cls):
        return "gce-image"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.image_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'sourceUri', str)
        self.copy_option(xml, 'description', str, optional = True)

    def show_type(self):
        return self.get_type()


class GCEImageState(ResourceState):
    """State of a GCE Image"""

    image_name = attr_property("gce.name", None)
    source_uri = attr_property("gce.sourceUri", None)
    description = attr_property("gce.description", None)

    @classmethod
    def get_type(cls):
        return "gce-image"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        return super(GCEImageState, self).show_type()

    @property
    def resource_id(self):
        return self.image_name

    nix_name = "gceImages"

    @property
    def full_name(self):
        return "GCE image '{0}'".format(self.image_name)

    def image(self):
        img = self.connect().ex_get_image(self.image_name)
        if img:
            img.destroy = img.delete
        return img

    defn_properties = [ 'description', 'source_uri' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'source_uri')
        self.no_property_change(defn, 'description')
        self.no_project_change(defn)

        self.copy_credentials(defn)
        self.image_name = defn.image_name

        if check:
            image = self.image()
            if image:
                if self.state == self.UP:
                    self.handle_changed_property('description', image.extra['description'], can_fix = False)
                else:
                    self.warn_not_supposed_to_exist(valuable_data = True)
                    self.confirm_destroy(image, self.full_name)
            else:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log("creating {0}...".format(self.full_name))
            try:
                image = self.connect().ex_copy_image(defn.image_name, defn.source_uri,
                                                     description = defn.description)
            except libcloud.common.google.ResourceExistsError:
                raise Exception("tried creating an image that already exists; "
                                "please run 'deploy --check' to fix this")
            self.state = self.UP
            self.copy_properties(defn)

    def destroy(self, wipe=False):
        if self.state == self.UP:
            image = self.image()
            if image:
                return self.confirm_destroy(image, self.full_name, abort = False)
            else:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
        return True
