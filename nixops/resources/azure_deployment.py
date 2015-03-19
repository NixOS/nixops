# -*- coding: utf-8 -*-

# Automatic provisioning of Azure deployments.

import os
import azure

from azure.servicemanagement import *
from nixops.util import attr_property, generate_random_string, check_wait
from nixops.azure_common import ResourceDefinition, ResourceState

class AzureDeploymentDefinition(ResourceDefinition):
    """Definition of an Azure Deployment"""

    @classmethod
    def get_type(cls):
        return "azure-deployment"

    def __init__(self, xml):
        ResourceDefinition.__init__(self, xml)

        self.deployment_name = self.get_option_value(xml, 'name', str)
        self.copy_option(xml, 'label', str, empty = False)
        self.copy_option(xml, 'ipAddress', 'resource', optional = True)
        self.copy_option(xml, 'hostedService', 'resource')
        self.copy_option(xml, 'dummyDiskUrl', str, empty = False)
        self.copy_option(xml, 'slot', str)
        if self.slot not in [ 'production', 'staging' ]:
            raise Exception('Deployment slot must be either "production" or "staging"')

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.slot)


class AzureDeploymentState(ResourceState):
    """State of an Azure Deployment"""

    public_ipv4 = attr_property("publicIpv4", None)

    deployment_name = attr_property("azure.name", None)
    label = attr_property("azure.label", None)
    slot = attr_property("azure.slot", None)
    ip_address = attr_property("azure.ipAddress", None)
    hosted_service = attr_property("azure.hostedService", None)

    dummy_root_disk = attr_property("azure.dummyRootDisk", None)

    @classmethod
    def get_type(cls):
        return "azure-deployment"

    def __init__(self, depl, name, id):
        ResourceState.__init__(self, depl, name, id)

    def show_type(self):
        s = super(AzureDeploymentState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.slot)
        return s

    @property
    def resource_id(self):
        return self.deployment_name

    nix_name = "azureDeployments"

    @property
    def full_name(self):
        return "Azure deployment '{0}'".format(self.resource_id)

    def get_resource(self):
        try:
            return self.sms().get_deployment_by_name(self.hosted_service, self.resource_id)
        except azure.WindowsAzureMissingResourceError:
            return None

    def destroy_resource(self):
        req = self.sms().delete_deployment(self.hosted_service, self.resource_id)
        self.finish_request(req)

    def is_deployed(self):
        return (self.state == self.UP) or (self.dummy_root_disk is not None)

    def is_settled(self, resource):
        return resource is None or (resource.status != 'Creating' and
                                    resource.status != 'Deleting')

    defn_properties = [ 'label', 'slot', 'ip_address' ]

    dummy_name = "dummy_to_be_deleted"

    def check_and_delete_dummy(self):
        try:
            vm = self.sms().get_role(self.hosted_service, self.deployment_name, self.dummy_name)
            self.log('found dummy VM in {0}; deleting...'.format(self.full_name))
            #FIXME: this functionality should be available via regular delete_role() call in future azure lib versions
            req = self.sms()._perform_delete( 
                self.sms()._get_role_path(self.hosted_service, self.deployment_name, self.dummy_name) + '?comp=media',
                async=True)
            self.finish_request(req)
        except azure.WindowsAzureMissingResourceError:
            return

    def deallocate_dummy(self):
      try:
        self.sms().shutdown_role(self.hosted_service, self.deployment_name, self.dummy_name,
                                 post_shutdown_action='StoppedDeallocated')
        vm = self.sms().get_role(self.hosted_service, self.deployment_name, self.dummy_name)
        self.dummy_root_disk = vm.os_virtual_hard_disk.disk_name
      except azure.WindowsAzureMissingResourceError:
        self.warn("dummy VM wasn't found in {0}".format(self.full_name))

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_property_change(defn, 'hosted_service')
        self.no_property_change(defn, 'label')
        self.no_property_change(defn, 'slot')
        self.no_property_change(defn, 'ip_address')

        self.copy_credentials(defn)
        self.deployment_name = defn.deployment_name
        self.hosted_service = defn.hosted_service

        if check:
            deployment = self.get_settled_resource()
            if not deployment:
                self.warn_missing_resource()
            elif self.state == self.UP:
                self.handle_changed_property('label', deployment.label, can_fix = False)
                self.handle_changed_property('slot', deployment.deployment_slot.lower(), can_fix = False)
                #FIXME: check the reserved ip
                self.deallocate_dummy()
            else:
                self.warn_not_supposed_to_exist()
                self.confirm_destroy()

        if self.state != self.UP:
            if self.get_settled_resource():
                raise Exception("tried creating a deployment that already exists; "
                                "please run 'deploy --check' to fix this")

            self.log("creating {0} in {1}...".format(self.full_name, defn.hosted_service))
            dummy_disk = OSVirtualHardDisk(
                source_image_name = 'b39f27a8b8c64d52b05eac6a62ebad85__Ubuntu-14_10-amd64-server-20150416-en-us-30GB',
                media_link = defn.dummy_disk_url)
            dummy_config = LinuxConfigurationSet(host_name = self.dummy_name,
                                                 user_name = 'dummy_user',
                                                 user_password = generate_random_string(length=32))
            network_config = ConfigurationSet()
            # deployment with a reserved IP must contain at least one input endpoint
            network_config.input_endpoints.input_endpoints.append(ConfigurationSetInputEndpoint('dummy', 'tcp', '60000', '60000'))
            req = self.sms().create_virtual_machine_deployment(defn.hosted_service, defn.deployment_name,
                                                               defn.slot, defn.label, self.dummy_name,
                                                               dummy_config, dummy_disk,
                                                               network_config = network_config,
                                                               role_size = 'ExtraSmall',
                                                               reserved_ip_name = defn.ip_address)
            self.finish_request(req)

            self.state = self.UP
            self.copy_properties(defn)
            self.public_ipv4 = defn.ip_address and self.sms().get_reserved_ip_address(defn.ip_address).address
            self.deallocate_dummy()


    def destroy(self, wipe=False):
        if wipe:
            log.warn("wipe is not supported")

        if self.state == self.UP:
            self.deallocate_dummy()
            resource = self.get_settled_resource()
            if resource:
                question = "are you sure you want to destroy {0}?"
                if not self.depl.logger.confirm(question.format(self.full_name)):
                    return False
                self.log("destroying...")
                self.destroy_resource()
            else:
                self.warn("tried to destroy {0} which didn't exist".format(self.full_name))

        if self.dummy_root_disk:
            self.log("destroying dummy root disk '{0}'...".format(self.dummy_root_disk))
            try:
                self.log("waiting for Azure disk {0} to detach...".format(self.dummy_root_disk))
                def check_detached():
                    return self.sms().get_disk(self.dummy_root_disk).attached_to is None
                check_wait(check_detached, initial=1, max_tries=100, exception=True)

                self.sms().delete_disk(self.dummy_root_disk, delete_vhd=True)
            except azure.WindowsAzureMissingResourceError:
                self.warn("seems to have been destroyed already")
            self.dummy_root_disk = None

        return True


    def create_after(self, resources, defn):
        from nixops.resources.azure_blob_container import AzureBLOBContainerState
        from nixops.resources.azure_storage import AzureStorageState
        from nixops.resources.azure_hosted_service import AzureHostedServiceState
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState) or
                  isinstance(r, AzureHostedServiceState) }
