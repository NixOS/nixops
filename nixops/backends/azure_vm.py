# -*- coding: utf-8 -*-

import os
import sys
import socket
import struct
import azure
import re
import base64

from azure.storage import BlobService
from azure.servicemanagement import *

from nixops import known_hosts
from nixops.util import wait_for_tcp_port, ping_tcp_port
from nixops.util import attr_property, create_key_pair, generate_random_string, check_wait
from nixops.nix_expr import Function, RawValue

from nixops.backends import MachineDefinition, MachineState
from nixops.azure_common import ResourceDefinition, ResourceState

from xml.etree import ElementTree

class AzureDefinition(MachineDefinition, ResourceDefinition):
    """
    Definition of an Azure machine.
    """
    @classmethod
    def get_type(cls):
        return "azure"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='azure']/attrs")
        assert x is not None

        self.copy_option(x, 'machineName', str)

        self.copy_option(x, 'subscriptionId', str)
        self.copy_option(x, 'certificatePath', str)

        self.copy_option(x, 'roleSize', str, empty = False)
        #self.copy_option(x, 'storage', 'resource')
        self.copy_option(x, 'hostedService', 'resource')
        self.copy_option(x, 'deployment', 'resource')

        self.copy_option(x, 'rootDiskImage', str, empty = False)
        self.copy_option(x, 'rootDiskUrl', str, empty = False)

        self.obtain_ip = self.get_option_value(x, 'obtainIP', bool)

        def parse_endpoint(xml, proto):
            return {
                'name': xml.get('name'),
                'protocol': proto,
                'port': self.get_option_value(xml, 'port', int),
                'local_port': self.get_option_value(xml, 'localPort', int),
                'set': self.get_option_value(xml, 'setName', str, optional = True),
                'dsr': self.get_option_value(xml, 'directServerReturn', bool)
            }

        ie_xml = x.find("attr[@name='inputEndpoints']/attrs")

        tcp_endpoints = [ parse_endpoint(k, "tcp")
                          for k in ie_xml.findall("attr[@name='tcp']/attrs/attr") ]
        udp_endpoints = [ parse_endpoint(k, "udp")
                          for k in ie_xml.findall("attr[@name='udp']/attrs/attr") ]

        self.input_endpoints = sorted(tcp_endpoints + udp_endpoints)

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.role_size or "???")


class AzureState(MachineState, ResourceState):
    """
    State of an Azure machine.
    """
    @classmethod
    def get_type(cls):
        return "azure"

    machine_name = attr_property("azure.name", None)
    public_ipv4 = attr_property("publicIpv4", None)

    role_size = attr_property("azure.roleSize", None)

    public_client_key = attr_property("azure.publicClientKey", None)
    private_client_key = attr_property("azure.privateClientKey", None)

    public_host_key = attr_property("azure.publicHostKey", None)
    private_host_key = attr_property("azure.privateHostKey", None)

    storage = attr_property("azure.storage", None)
    hosted_service = attr_property("azure.hostedService", None)
    deployment = attr_property("azure.deployment", None)

    obtain_ip = attr_property("azure.obtain_ip", None, bool)

    input_endpoints = attr_property("azure.input_endpoints", {}, 'json')
    block_device_mapping = attr_property("azure.blockDeviceMapping", {}, 'json')
    root_disk = attr_property("azure.rootDisk", None)

    backups = attr_property("azure.backups", {}, 'json')

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._sms = None
        self._bs = None

    @property
    def resource_id(self):
        return self.machine_name

    def show_type(self):
        s = super(AzureState, self).show_type()
        return "{0} [{1}]".format(s, self.role_size)

    credentials_prefix = "deployment.azure"

    @property
    def full_name(self):
        return "Azure machine '{0}'".format(self.machine_name)

    def bs(self):
        if not self._bs:
            storage_resource = next((r for r in self.depl.resources.values()
                                       if getattr(r, 'storage_name', None) == self.storage), None)
            self._bs = BlobService(self.storage, storage_resource.access_key)
        return self._bs

    def _delete_volume(self, volume_id, allow_keep=False):
        if not self.depl.logger.confirm("are you sure you want to destroy Azure disk '{0}'?".format(volume_id)):
            if allow_keep:
                return
            else:
                raise Exception("not destroying Azure disk '{0}'".format(volume_id))
        self.log("destroying Azure disk '{0}'...".format(volume_id))
        try:
            self.log("waiting for Azure disk {0} to detach...".format(volume_id))
            def check_detached():
                return self.sms().get_disk(volume_id).attached_to is None
            check_wait(check_detached, initial=1, max_tries=100, exception=True)

            self.sms().delete_disk(volume_id, delete_vhd=True)
        except azure.WindowsAzureMissingResourceError:
            self.warn("seems to have been destroyed already")


    def _node_deleted(self):
        self.vm_id = None
        self.state = self.STOPPED


    defn_properties = [ 'role_size', 'input_endpoints', 'obtain_ip' ]

    def is_deployed(self):
        return (self.vm_id or self.block_device_mapping or self.root_disk)

    def get_resource(self):
        try:
            return self.sms().get_role(self.hosted_service, self.deployment, self.resource_id)
        except azure.WindowsAzureMissingResourceError:
            return None

    def destroy_resource(self):
        req = self.sms().delete_role(self.hosted_service, self.deployment, self.resource_id)
        self.finish_request(req)


    def is_settled(self, resource):
        return True

    def fetch_PIP(self):
        d = self.sms().get_deployment_by_name(self.hosted_service, self.deployment)
        instance = next((r for r in d.role_instance_list if r.instance_name == self.machine_name), None)
        return (instance and instance.public_ips and instance.public_ips[0].address)

    def mk_network_configuration(self, endpoints):
        network_configuration = ConfigurationSet()
        for ie in endpoints:
            network_configuration.input_endpoints.input_endpoints.append(ConfigurationSetInputEndpoint(
                name = ie['name'],
                protocol = ie['protocol'],
                port = ie['port'],
                local_port = ie['local_port'],
                load_balanced_endpoint_set_name = ie['set'],
                enable_direct_server_return = ie['dsr'] ))
        return network_configuration

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(self.machine_name != defn.machine_name, "instance name")
        self.no_property_change(defn, 'hosted_service')
        self.no_property_change(defn, 'deployment')

        self.set_common_state(defn)
        self.copy_credentials(defn)
        self.machine_name = defn.machine_name
        #self.storage = defn.storage
        self.hosted_service = defn.hosted_service
        self.deployment = defn.deployment

        if not self.public_client_key:
            (private, public) = create_key_pair()
            self.public_client_key = public
            self.private_client_key = private

        if not self.public_host_key:
            (private, public) = create_key_pair(type="ecdsa")
            self.public_host_key = public
            self.private_host_key = private

        if check:
            vm = self.get_settled_resource()
            if vm:
                self.root_disk = vm.os_virtual_hard_disk.disk_name
                if self.vm_id:  
                    self.handle_changed_property('public_ipv4', self.fetch_PIP())
                    self.update_ssh_known_hosts()

                    net_cfg = vm.configuration_sets[0]
                    assert net_cfg.configuration_set_type == 'NetworkConfiguration'
                    def normalize_empty(x):
                        return (x if x != "" else None)
                    ies = []
                    for ie in net_cfg.input_endpoints:
                        ies.append({
                            'protocol': ie.protocol,
                            'name': ie.name,
                            'port': int(ie.port),
                            'local_port': int(ie.local_port),
                            'dsr': ie.enable_direct_server_return,
                            'set': normalize_empty(ie.load_balanced_endpoint_set_name) })
                    self.handle_changed_property('input_endpoints', sorted(ies))
                else:
                    self.warn_not_supposed_to_exist(valuable_data = True)
                    self.confirm_destroy()
            else:
                if self.vm_id:
                    self.warn("the instance seems to have been destroyed behind our back")
                    if not allow_recreate: raise Exception("use --allow-recreate to fix")
                    self._node_deleted()

        if self.vm_id and defn.role_size != self.role_size and not allow_reboot:
            raise Exception("reboot is required to change role size; please run with --allow-reboot")

        self.create_node(defn)

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            network_configuration = self.mk_network_configuration(defn.input_endpoints)
            if defn.obtain_ip:
                network_configuration.public_ips.public_ips.append(PublicIP(name = "public"))
            req = self.sms().update_role(defn.hosted_service, defn.deployment, defn.machine_name,
                                         network_config = network_configuration,
                                         role_size = defn.role_size)
            self.finish_request(req)
            self.copy_properties(defn)

            new_ip = self.fetch_PIP()
            if self.public_ipv4 != new_ip:
                self.log("got IP: {0}".format(new_ip))
            self.public_ipv4 = new_ip
            self.update_ssh_known_hosts()

    def create_node(self, defn):
        if not self.vm_id:
            if self.get_settled_resource():
                raise Exception("tried creating a virtual machine that already exists; "
                                "please run 'deploy --check' to fix this")
            self.log("creating {0}...".format(self.full_name))

            custom_data = ('ssh_host_ecdsa_key=$(cat<<____HERE\n{0}\n____HERE\n)\n'
                           'ssh_host_ecdsa_key_pub="{1}"\nssh_root_auth_key="{2}"\n'
                          ).format(self.private_host_key, self.public_host_key, self.public_client_key)
            config = LinuxConfigurationSet(host_name = defn.machine_name,
                                           user_name = 'user', user_password = 'paSS55',
                                           disable_ssh_password_authentication = False,
                                           custom_data = base64.b64encode(custom_data))

            root_disk = OSVirtualHardDisk(source_image_name = defn.root_disk_image,
                                          media_link = defn.root_disk_url)
            network_configuration = self.mk_network_configuration(defn.input_endpoints)
            if defn.obtain_ip:
                network_configuration.public_ips.public_ips.append(PublicIP(name = "public"))

            req = self.sms().add_role(defn.hosted_service, defn.deployment, defn.machine_name,
                                      config, root_disk,
                                      availability_set_name = None,
                                      data_virtual_hard_disks = None,
                                      network_config = network_configuration,
                                      role_size = defn.role_size)
            self.finish_request(req)

            self.vm_id = self.machine_name
            self.state = self.STARTING
            self.ssh_pinged = False
            self.copy_properties(defn)

            vm = self.get_resource()
            self.root_disk = vm.os_virtual_hard_disk.disk_name

            self.public_ipv4 = self.fetch_PIP()
            self.log("got IP: {0}".format(self.public_ipv4))
            self.update_ssh_known_hosts()


    def reboot(self, hard=False):
        if hard:
            self.log("sending hard reset to Azure machine...")
            self.node().reboot()
            self.sms().restart_role(self.hosted_service, self.deployment, self.machine_name)
            #FIXME: how is it different from reboot_role_instance?
            self.state = self.STARTING
        else:
            MachineState.reboot(self, hard=hard)

    def start(self):
        if self.vm_id:
            self.state = self.STARTING
            self.log("starting Azure machine...")
            req = self.sms().start_role(self.hosted_service, self.deployment, self.machine_name)
            self.finish_request(req)
            self.wait_for_ssh(check=True)
            self.send_keys()

    def stop(self):
        if self.vm_id:
           #FIXME: there's also "stopped deallocated" version of this. how to integrate?
            self.log("stopping Azure machine... ")
            req = self.sms().shutdown_role(self.hosted_service, self.deployment, self.machine_name)
            self.finish_request(req)
            self.ssh.reset()

    def destroy(self, wipe=False):
        if wipe:
            log.warn("wipe is not supported")

        if self.vm_id:
            vm = self.get_resource()
            if vm:
                question = "are you sure you want to destroy {0}?"
                if not self.depl.logger.confirm(question.format(self.full_name)):
                    return False
                self.log("destroying the Azure machine...")
                self.destroy_resource()
            else:
                self.warn("seems to have been destroyed already")
        self._node_deleted()

        # Destroy volumes created for this instance.
        if self.root_disk:
            self._delete_volume(self.root_disk)
            self.root_disk = None

        return True

    def get_physical_spec(self):
        return {
            'require': [
                RawValue("<nixpkgs/nixos/modules/virtualisation/azure-config.nix>")
            ],
        }

    def create_after(self, resources, defn):
        from nixops.resources.azure_blob import AzureBLOBState
        from nixops.resources.azure_blob_container import AzureBLOBContainerState
        from nixops.resources.azure_storage import AzureStorageState
        from nixops.resources.azure_reserved_ip_address import AzureReservedIPAddressState
        from nixops.resources.azure_hosted_service import AzureHostedServiceState
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState) or
                     isinstance(r, AzureBLOBState) or isinstance(r, AzureReservedIPAddressState) or 
                     isinstance(r, AzureHostedServiceState)}

    def find_ssh_endpoint(self):
        return next((ie for ie in self.input_endpoints
                        if ie.get('local_port', 0) == 22), None)

    def get_deployment_IP(self):
        deployment_resource = (self.deployment and
                               next((r for r in self.depl.resources.values()
                                       if getattr(r, 'deployment_name', None) == self.deployment), None))
        return (deployment_resource and deployment_resource.public_ipv4)

    def get_ssh_host_port(self):
        if self.public_ipv4:
            return self.public_ipv4
        ep = self.find_ssh_endpoint()
        ip = self.get_deployment_IP()
        if ip is not None and ep is not None and ep.get('port', None) is not None:
            return "[{0}]:{1}".format(ip, ep.get('port'))
        else:
            return None

    @MachineState.ssh_port.getter
    def ssh_port(self):
        if self.public_ipv4:
            return super(AzureState, self).ssh_port
        else:
            ep = self.find_ssh_endpoint()
            return (ep is not None and ep.get('port', None))

    def update_ssh_known_hosts(self):
        ssh_host_port = self.get_ssh_host_port()
        if ssh_host_port:
            known_hosts.add(ssh_host_port, self.public_host_key)

    def get_ssh_name(self):
        ip = self.public_ipv4 or (self.find_ssh_endpoint() and self.get_deployment_IP())
        if ip is None:
            raise Exception("{0} does not have a public IPv4 address and is not reachable "
                            "via an input endpoint on its deployment IP address"
                            .format(self.full_name))
        return ip

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.private_client_key)

    def get_ssh_flags(self, scp=False):
        port_flags = []
        if self.public_ipv4 is None:
            ep = self.find_ssh_endpoint()
            if ep is not None:
                port_flags = [ '-p', str(ep.get('port', 0)) ]

        return [ "-i", self.get_ssh_private_key_file() ] + port_flags
