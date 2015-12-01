# -*- coding: utf-8 -*-

# Automatic provisioning of Azure affinity groups.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState


class AzureAffinityGroupDefinition(ResourceDefinition):
    """Definition of an Azure Affinity Group"""

    @classmethod
    def get_type(cls):
        return "azure-affinity-group"

    @classmethod
    def get_resource_type(cls):
        return "azureAffinityGroups"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.affinity_group_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'location', str, empty = False)
        self.copy_option(xml, 'label', str, empty = False)
        self.copy_option(xml, 'description', str)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.location)


class AzureAffinityGroupState(ResourceState):
    """State of an Azure Affinity Group"""

    affinity_group_name = attr_property("azure.name", None)
    location = attr_property("azure.location", None)
    label = attr_property("azure.label", None)
    description = attr_property("azure.description", None)

    @classmethod
    def get_type(cls):
        return "azure-affinity-group"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(AzureAffinityGroupState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.location)
        return s

    @property
    def resource_id(self):
        return self.affinity_group_name

    nix_name = "azureAffinityGroups"

    @property
    def full_name(self):
        return "Azure affinity group '{0}'".format(self.affinity_group_name)

    def get_resource(self):
        try:
            return self.sms().get_affinity_group_properties(self.affinity_group_name)
        except azure.WindowsAzureMissingResourceError:
            return None

    def destroy_resource(self):
        self.sms().delete_affinity_group(self.affinity_group_name)

    def is_settled(self, resource):
        return True

    defn_properties = [ 'description', 'label', 'location' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')

        self.copy_credentials(defn)
        self.affinity_group_name = defn.affinity_group_name

        if check:
            ag = self.get_settled_resource()
            if not ag:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location', ag.location, can_fix = False)
                self.handle_changed_property('label', ag.label)
                self.handle_changed_property('description', ag.description)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating an affinity group that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            self.sms().create_affinity_group(defn.affinity_group_name,
                                              defn.label, defn.location,
                                              description = defn.description)
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self.sms().update_affinity_group(self.affinity_group_name, defn.label,
                                              description = defn.description)
            self.copy_properties(defn)
