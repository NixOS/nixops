# -*- coding: utf-8 -*-

# Automatic provisioning of Azure hosted services.

import os
import azure

from nixops.util import attr_property
from nixops.azure_common import ResourceDefinition, ResourceState

def normalize_empty(x):
    return x if x != "" else None

class AzureHostedServiceDefinition(ResourceDefinition):
    """Definition of an Azure Hosted Service"""

    @classmethod
    def get_type(cls):
        return "azure-hosted-service"

    @classmethod
    def get_resource_type(cls):
        return "azureHostedServices"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.hosted_service_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'label', str, empty = False)
        self.copy_option(xml, 'description', str)
        self.copy_option(xml, 'affinityGroup', 'resource', optional = True)
        self.copy_option(xml, 'location', str, optional = True)
        self.location = normalize_empty(self.location)
        self.extended_properties = {
            k.get("name"): k.find("string").get("value")
            for k in xml.findall("attrs/attr[@name='extendedProperties']/attrs/attr")
        }
        if not self.location and not self.affinity_group:
            raise Exception("Location or affinity_group must be specified")
        if self.location and self.affinity_group:
            raise Exception("Only one of location or affinity group needs to be specified")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.affinity_group or self.location)


class AzureHostedServiceState(ResourceState):
    """State of an Azure Hosted Service"""

    hosted_service_name = attr_property("azure.name", None)
    location = attr_property("azure.location", None)
    label = attr_property("azure.label", None)
    description = attr_property("azure.description", None)
    affinity_group = attr_property("azure.affinityGroup", None)
    extended_properties = attr_property("azure.extendedProperties", {}, 'json')

    @classmethod
    def get_type(cls):
        return "azure-hosted-service"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(AzureHostedServiceState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.affinity_group or self.location)
        return s

    @property
    def resource_id(self):
        return self.hosted_service_name

    nix_name = "azureHostedServices"

    @property
    def full_name(self):
        return "Azure hosted service '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.sms().get_hosted_service_properties(self.resource_id)
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        req = self.sms().delete_hosted_service(self.resource_id)
        self.finish_request(req)

    def is_settled(self, resource):
        return resource is None or (resource.hosted_service_properties.status != 'Creating' and
                                    resource.hosted_service_properties.status != 'Deleting')

    defn_properties = [ 'label', 'location', 'description', 'affinity_group', 'extended_properties' ]

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'location')
        self.no_property_change(defn, 'affinity_group')

        self.copy_credentials(defn)
        self.hosted_service_name = defn.hosted_service_name

        if check:
            hs = self.get_settled_resource()
            if not hs:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('location',
                                             normalize_empty(hs.hosted_service_properties.location),
                                             can_fix = False)
                self.handle_changed_property('affinity_group',
                                             normalize_empty(hs.hosted_service_properties.affinity_group),
                                             can_fix = False)
                self.handle_changed_property('label', hs.hosted_service_properties.label)
                self.handle_changed_property('description', hs.hosted_service_properties.description)
                filtered_properties = { k : v
                                        for k, v in hs.hosted_service_properties.extended_properties.items()
                                        if k not in ['ResourceGroup', 'ResourceLocation'] }
                self.handle_changed_property('extended_properties', filtered_properties)
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a hosted service that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.location or defn.affinity_group))
            req = self.sms().create_hosted_service(defn.hosted_service_name, defn.label,
                                             description = defn.description,
                                             location = defn.location,
                                             affinity_group = defn.affinity_group,
                                             extended_properties = defn.extended_properties)
            self.finish_request(req)
            self.state = self.UP
            self.copy_properties(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            if not self.get_settled_resource():
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            self.sms().update_hosted_service(self.hosted_service_name, label = defn.label,
                                              description = defn.description,
                                              extended_properties = defn.extended_properties)
            self.copy_properties(defn)


    def create_after(self, resources, defn):
        from nixops.resources.azure_affinity_group import AzureAffinityGroupState
        return {r for r in resources
                  if isinstance(r, AzureAffinityGroupState)}
