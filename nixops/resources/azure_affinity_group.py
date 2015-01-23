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

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.affinity_group_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'location', str)
        self.copy_option(xml, 'label', str)
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

    defn_properties = [ 'description', 'label', 'location' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')

        self.copy_credentials(defn)
        self.affinity_group_name = defn.affinity_group_name

        if check:
            try:
                ag = self.sms().get_affinity_group_properties(self.affinity_group_name)
                if self.state == self.UP:
                    self.handle_changed_property('location', ag.location, can_fix = False)
                    self.handle_changed_property('label', ag.label)
                    self.handle_changed_property('description', ag.description)
                else:
                    self.warn_not_supposed_to_exist()
                    if self.depl.logger.confirm("are you sure you want to destroy {0}?".format(self.full_name)):
                        self.log("destroying...")
                        self.sms().delete_affinity_group(self.affinity_group_name)
                    else:
                        raise Exception("can't proceed further")

            except azure.WindowsAzureMissingResourceError:
                self.warn_missing_resource()

        if self.state != self.UP:
            self.log("creating {0} in {1}...".format(self.full_name, defn.location))
            try:
                ag = self.sms().create_affinity_group(defn.affinity_group_name,
                                                      defn.label, defn.location,
                                                      description = defn.description)
            except azure.WindowsAzureConflictError:
                raise Exception("tried creating an affinity group that already exists; "
                                "please run 'deploy --check' to fix this")

            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            try:
                self.depl.logger.confirm('about to update')
                self.sms().update_affinity_group(self.affinity_group_name, defn.label,
                                                 description = defn.description)
                self.copy_properties(defn)
            except azure.WindowsAzureError:
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))


    def destroy(self, wipe=False):
        if self.state == self.UP:
            try:
                self.sms().get_affinity_group_properties(self.affinity_group_name)
                if self.depl.logger.confirm("are you sure you want to destroy {0} ({1})?".format(self.full_name, self.location)):
                    self.log("destroying...")
                    self.sms().delete_affinity_group(self.affinity_group_name)
                    return True
                else:
                    return False
            except azure.WindowsAzureMissingResourceError:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))
        return True
