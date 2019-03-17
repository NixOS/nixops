# -*- coding: utf-8 -*-
# This file is named azure_vm.py instead of azure.py to avoid a namespace clash with azure library

import os
import sys
import socket
import struct
import azure
import re
import base64
import random
import threading

from azure.storage.blob import BlobService

import nixops
from nixops import known_hosts
from nixops.util import wait_for_tcp_port, ping_tcp_port
from nixops.util import attr_property, create_key_pair, generate_random_string, check_wait
from nixops.nix_expr import Call, RawValue

from nixops.backends import MachineDefinition, MachineState
from nixops.azure_common import ResourceDefinition, ResourceState, ResId, normalize_location

from azure.mgmt.network import PublicIpAddress, NetworkInterface, NetworkInterfaceIpConfiguration, IpAllocationMethod, PublicIpAddressDnsSettings, ResourceId
from azure.mgmt.compute import *

from nixops.resources.azure_availability_set import AzureAvailabilitySetState
from nixops.resources.azure_blob import AzureBLOBState
from nixops.resources.azure_blob_container import AzureBLOBContainerState
from nixops.resources.azure_directory import AzureDirectoryState
from nixops.resources.azure_file import AzureFileState
from nixops.resources.azure_load_balancer import AzureLoadBalancerState
from nixops.resources.azure_network_security_group import AzureNetworkSecurityGroupState
from nixops.resources.azure_queue import AzureQueueState
from nixops.resources.azure_reserved_ip_address import AzureReservedIPAddressState
from nixops.resources.azure_resource_group import AzureResourceGroupState
from nixops.resources.azure_share import AzureShareState
from nixops.resources.azure_storage import AzureStorageState
from nixops.resources.azure_table import AzureTableState
from nixops.resources.azure_virtual_network import AzureVirtualNetworkState


def device_name_to_lun(device):
    match = re.match(r'/dev/disk/by-lun/(\d+)$', device)
    return  None if match is None or int(match.group(1))>31 else int(match.group(1) )

def lun_to_device_name(lun):
    return ('/dev/disk/by-lun/' + str(lun))

def defn_find_root_disk(block_device_mapping):
   return next((d_id for d_id, d in block_device_mapping.iteritems()
                  if d['device'] == '/dev/sda'), None)

# when we look for the root disk in the deployed state,
# we must check that the disk is actually attached,
# because an unattached old root disk may still be around
def find_root_disk(block_device_mapping):
   return next((d_id for d_id, d in block_device_mapping.iteritems()
                  if d['device'] == '/dev/sda' and not d.get('needs_attach', False)), None)

def parse_blob_url(blob):
    match = re.match(r'https?://([^\./]+)\.[^/]+/([^/]+)/(.+)$', blob)
    return None if match is None else {
        "storage": match.group(1),
        "container": match.group(2),
        "name": match.group(3)
    }


class AzureDefinition(MachineDefinition, ResourceDefinition):
    """
    Definition of an Azure machine.
    """
    @classmethod
    def get_type(cls):
        return "azure"

    @property
    def credentials_prefix(self):
      return "deployment.azure"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)

        x = xml.find("attrs/attr[@name='azure']/attrs")
        assert x is not None

        self.copy_option(x, 'machineName', str)

        self.copy_credentials(x)

        self.copy_option(x, 'size', str, empty = False)
        self.copy_location(x)
        self.copy_option(x, 'storage', 'resource')
        self.copy_option(x, 'resourceGroup', 'resource')

        self.copy_option(x, 'rootDiskImageBlob', 'resource')
        self.copy_option(x, 'ephemeralDiskContainer', 'resource', optional = True)

        self.copy_option(x, 'availabilitySet', 'res-id', optional = True)
        self.copy_option(x, 'usePrivateIpAddress', bool, optional = True)

        ifaces_xml = x.find("attr[@name='networkInterfaces']")
        if_xml = ifaces_xml.find("attrs/attr[@name='default']")
        self.copy_option(if_xml, 'securityGroup', 'res-id', optional = True)

        ip_xml = if_xml.find("attrs/attr[@name='ip']")
        self.obtain_ip = self.get_option_value(ip_xml, 'obtain', bool)
        self.ip_domain_name_label = self.get_option_value(ip_xml, 'domainNameLabel', str, optional = True)
        self.ip_allocation_method = self.get_option_value(ip_xml, 'allocationMethod', str)
        self.ip_resid = self.get_option_value(ip_xml, 'resource', 'res-id', optional = True)

        if self.ip_resid and self.obtain_ip:
            raise Exception("{0}: must set ip.obtain = false to use a reserved IP address"
                            .format(self.machine_name))
        if self.obtain_ip:
            self.ip_resid = ResId("",
                                  subscription = self.get_subscription_id(),
                                  group = self.resource_group,
                                  provider = 'Microsoft.Network',
                                  type = 'publicIPAddresses',
                                  resource = self.machine_name).id

        subnet_xml  = if_xml.find("attrs/attr[@name='subnet']")
        self.subnet = ResId(self.get_option_value(subnet_xml, 'network', 'res-id'),
                            subresource = self.get_option_value(subnet_xml, 'name', str),
                            subtype = 'subnets').id

        self.backend_address_pools = [
            ResId(self.get_option_value(_x, 'loadBalancer', 'res-id'),
                  subresource = self.get_option_value(_x, 'name', str),
                  subtype = 'backendAddressPools').id
            for _x in if_xml.findall("attrs/attr[@name='backendAddressPools']/list/attrs")]

        self.inbound_nat_rules = [
            ResId(self.get_option_value(_x, 'loadBalancer', 'res-id'),
                  subresource = self.get_option_value(_x, 'name', str),
                  subtype = 'inboundNatRules').id
            for _x in if_xml.findall("attrs/attr[@name='inboundNatRules']/list/attrs")]

        def opt_disk_name(dname):
            return ("{0}-{1}".format(self.machine_name, dname) if dname is not None else None)

        def parse_block_device(xml):
            disk_name = self.get_option_value(xml, 'name', str)

            media_link = self.get_option_value(xml, 'mediaLink', str, optional = True)
            if not media_link and self.ephemeral_disk_container:
                media_link = ( "https://{0}.blob.core.windows.net/{1}/{2}-{3}.vhd"
                               .format(self.storage, self.ephemeral_disk_container,
                                       self.machine_name, disk_name))
            if not media_link:
                raise Exception("{0}: ephemeral disk {1} must specify mediaLink"
                                .format(self.machine_name, disk_name))
            blob = parse_blob_url(media_link)
            if not blob:
                raise Exception("{0}: malformed BLOB URL {1}"
                                .format(self.machine_name, media_link))
            if media_link[:5] == 'http:':
                raise Exception("{0}: please use https in BLOB URL {1}"
                                .format(self.machine_name, media_link))
            if self.storage != blob['storage']:
                raise Exception("{0}: expected storage to be {1} in BLOB URL {2}"
                                .format(self.machine_name, self.storage, media_link))
            return {
                'name': disk_name,
                'device': xml.get("name"),
                'media_link': media_link,
                'size': self.get_option_value(xml, 'size', int, optional = True),
                'is_ephemeral': self.get_option_value(xml, 'isEphemeral', bool),
                'host_caching': self.get_option_value(xml, 'hostCaching', str),
                'encrypt': self.get_option_value(xml, 'encrypt', bool),
                'passphrase': self.get_option_value(xml, 'passphrase', str)
            }

        devices = [ parse_block_device(_d)
                    for _d in x.findall("attr[@name='blockDeviceMapping']/attrs/attr") ]
        self.block_device_mapping = { _d['media_link']: _d for _d in devices }

        media_links = [ _d['media_link'] for _d in devices ]
        if len(media_links) != len(set(media_links)):
            raise Exception("{0} has duplicate disk BLOB URLs".format(self.machine_name))

        for d_id, disk in self.block_device_mapping.iteritems():
            if disk['device'] != "/dev/sda" and device_name_to_lun(disk['device']) is None:
                raise Exception("{0}: blockDeviceMapping only supports /dev/sda and "
                                "/dev/disk/by-lun/X block devices, where X is in 0..31 range"
                                .format(self.machine_name))
        if defn_find_root_disk(self.block_device_mapping) is None:
            raise Exception("{0} needs a root disk".format(self.machine_name))


    def show_type(self):
        return "{0} [{1}; {2}]".format(self.get_type(), self.location or "???", self.size or "???")


class AzureState(MachineState, ResourceState):
    """
    State of an Azure machine.
    """
    @classmethod
    def get_type(cls):
        return "azure"

    machine_name = attr_property("azure.name", None)
    public_ipv4 = attr_property("publicIpv4", None)
    private_ipv4 = attr_property("privateIpv4", None)
    use_private_ip_address = attr_property("azure.usePrivateIpAddress", False, type=bool)

    size = attr_property("azure.size", None)
    location = attr_property("azure.location", None)

    public_client_key = attr_property("azure.publicClientKey", None)
    private_client_key = attr_property("azure.privateClientKey", None)

    public_host_key = attr_property("azure.publicHostKey", None)
    private_host_key = attr_property("azure.privateHostKey", None)

    storage = attr_property("azure.storage", None)
    subnet = attr_property("azure.subnet", None)
    backend_address_pools = attr_property("azure.backendAddressPools", [], 'json')
    inbound_nat_rules = attr_property("azure.inboundNatRules", [], 'json')
    resource_group = attr_property("azure.resourceGroup", None)

    obtain_ip = attr_property("azure.obtainIP", None, bool)
    ip_domain_name_label = attr_property("azure.ipDomainNameLabel", None)
    ip_resid = attr_property("azure.ipResId", None)
    ip_allocation_method = attr_property("azure.ipAllocationMethod", None)
    security_group = attr_property("azure.securityGroup", None)
    availability_set = attr_property("azure.availabilitySet", None)

    block_device_mapping = attr_property("azure.blockDeviceMapping", {}, 'json')
    generated_encryption_keys = attr_property("azure.generatedEncryptionKeys", {}, 'json')

    backups = attr_property("azure.backups", {}, 'json')

    public_ip = attr_property("azure.publicIP", None)
    network_interface = attr_property("azure.networkInterface", None)

    known_ssh_host_port = attr_property("azure.knownSshHostPort", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        ResourceState.__init__(self, depl, name, id)
        self._bs = None

    @property
    def resource_id(self):
        return self.machine_name

    def show_type(self):
        s = super(AzureState, self).show_type()
        return "{0} [{1}; {2}]".format(s, self.location or "???", self.size or "???")

    @property
    def full_name(self):
        return "Azure machine '{0}'".format(self.machine_name)

    def bs(self):
        if not self._bs:
            storage_resource = next((r for r in self.depl.resources.values()
                                       if getattr(r, 'storage_name', None) == self.storage), None)
            self._bs = BlobService(self.storage, storage_resource.access_key)
        return self._bs

    # delete_vhd = None: ask the user
    def _delete_volume(self, media_link, disk_name = None, delete_vhd = None):
        if media_link is None:
            self.warn("attempted to delete a disk without a BLOB URL; this is a bug")
            return
        try:
            if delete_vhd or (delete_vhd is None and
                              self.depl.logger.confirm("are you sure you want to destroy "
                                                       "the contents(BLOB) of Azure disk {0}({1})?"
                                                       .format(disk_name, media_link)) ):
                self.log("destroying Azure disk BLOB {0}...".format(media_link))
                blob = parse_blob_url(media_link)
                if blob is None:
                    raise Exception("failed to parse BLOB URL {0}".format(media_link))
                if blob["storage"] != self.storage:
                    raise Exception("storage {0} provided in the deployment specification "
                                    "doesn't match the storage of BLOB {1}"
                                    .format(self.storage, media_link))
                try:
                    self.bs().delete_blob(blob["container"], blob["name"])
                except azure.common.AzureConflictHttpError as e:
                    if "<Error><Code>SnapshotsPresent</Code><Message>" in e.message:
                        if not self.depl.logger.confirm(
                                  "the BLOB of Azure disk {0}({1}) has snapshots(backups); "
                                  "deleting the disk BLOB also deletes snapshots; "
                                  "keep the disk contents(BLOB)?"
                                  .format(disk_name, media_link)):
                            self.log("destroying Azure disk BLOB {0} and its snapshots..."
                                     .format(media_link))
                            self.bs().delete_blob(blob["container"], blob["name"],
                                                  x_ms_delete_snapshots = 'include')
                        else:
                            self.log("keeping the Azure disk BLOB {0}..."
                                     .format(media_link))
                    else:
                        raise e
            else:
                self.log("keeping the Azure disk BLOB {0}...".format(media_link))

        except azure.common.AzureMissingResourceHttpError:
            self.warn("seems to have been destroyed already")

    def blob_exists(self, media_link):
        try:
            blob = parse_blob_url(media_link)
            if blob["storage"] != self.storage:
                raise Exception("storage {0} provided in the deployment specification "
                                "doesn't match the storage of BLOB {1}"
                                .format(self.storage, media_link))
            if blob is None:
                raise Exception("failed to parse BLOB URL {0}".format(media_link))
            self.bs().get_blob_properties(blob["container"], blob["name"])
            return True
        except azure.common.AzureMissingResourceHttpError:
            return False

    def _delete_encryption_key(self, disk_id):
        if self.generated_encryption_keys.get(disk_id, None) == None:
            return
        if self.depl.logger.confirm("Azure disk {0} has an automatically generated encryption key; "
                                    "if the key is deleted, the data will be lost even if you have "
                                    "a copy of the disk contents; "
                                    "are you sure you want to delete the encryption key?"
                                   .format(disk_id) ):
            self.update_generated_encryption_keys(disk_id, None)


    def _node_deleted(self):
        self.vm_id = None
        self.state = self.STOPPED
        for d_id, disk in self.block_device_mapping.iteritems():
            disk['needs_attach'] = True
            self.update_block_device_mapping(d_id, disk)
        if self.known_ssh_host_port and self.public_host_key:
            known_hosts.remove(self.known_ssh_host_port, self.public_host_key)
            self.known_ssh_host_port = None
        self.public_ipv4 = None


    defn_properties = [ 'size', 'availability_set', 'use_private_ip_address' ]

    def is_deployed(self):
        return (self.vm_id or self.block_device_mapping or self.public_ip or self.network_interface)

    def get_resource(self):
        try:
            vm = self.cmc().virtual_machines.get(self.resource_group, self.resource_id).virtual_machine
            # workaround: if set to [], azure throws an error if we reuse the VM object in update requests
            if vm.extensions == []:
                vm.extensions = None
            return vm
        except azure.common.AzureMissingResourceHttpError:
            return None

    def destroy_resource(self):
        self.cmc().virtual_machines.delete(self.resource_group, self.resource_id)

    def fetch_public_ip(self):
        ip_resid = self.ip_resid and ResId(self.ip_resid)
        return self.ip_resid and self.nrpc().public_ip_addresses.get(
                   ip_resid['group'], ip_resid['resource']).public_ip_address.ip_address

    def fetch_private_ip(self):
        return self.network_interface and self.nrpc().network_interfaces.get(
                   self.resource_group, self.network_interface).network_interface.ip_configurations[0].private_ip_address

    def update_block_device_mapping(self, k, v):
        x = self.block_device_mapping
        if v == None:
            x.pop(k, None)
        else:
            x[k] = v
        self.block_device_mapping = x

    def update_generated_encryption_keys(self, k, v):
        x = self.generated_encryption_keys
        if v == None:
            x.pop(k, None)
        else:
            x[k] = v
        self.generated_encryption_keys = x


    def check_network_iface(self):
        try:
            iface = self.nrpc().network_interfaces.get(self.resource_group, self.machine_name).network_interface
        except azure.common.AzureMissingResourceHttpError:
            iface = None
        if iface:
            ip_resid = iface.ip_configurations[0].public_ip_address
            self.handle_changed_property('ip_resid', ip_resid and ip_resid.id,
                                         property_name = "IP resource ID")
            self.handle_changed_property('subnet', iface.ip_configurations[0].subnet.id)
            self.handle_changed_property('security_group', iface.network_security_group and
                                                           iface.network_security_group.id)
            backend_address_pools = [ r.id for r in iface.ip_configurations[0].load_balancer_backend_address_pools ]
            self.handle_changed_property('backend_address_pools', sorted(backend_address_pools))
            inbound_nat_rules = [ r.id for r in iface.ip_configurations[0].load_balancer_inbound_nat_rules ]
            self.handle_changed_property('inbound_nat_rules', sorted(inbound_nat_rules))
        elif self.network_interface:
            self.warn("network interface has been destroyed behind our back")
            self.network_interface = None

    def check_ip(self):
        if not self.public_ip: return
        try:
            ip = self.nrpc().public_ip_addresses.get(self.resource_group, self.public_ip).public_ip_address
        except azure.common.AzureMissingResourceHttpError:
            ip = None
        if ip:
            _dns = ip.dns_settings
            self.handle_changed_property('ip_domain_name_label',
                                         _dns and _dns.domain_name_label)
            self.handle_changed_property('ip_allocation_method',
                                         ip.public_ip_allocation_method)
        else:
            self.warn("IP address has been destroyed behind our back")
            self.public_ip = None

    def delete_ip_address(self):
        if self.public_ip:
            self.log("releasing the ip address...")
            try:
                self.nrpc().public_ip_addresses.get(self.resource_group, self.public_ip)
                self.nrpc().public_ip_addresses.delete(self.resource_group, self.public_ip)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("seems to have been released already")
            self.public_ip = None

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_subscription_id_change(defn)
        self.no_change(self.machine_name != defn.machine_name, "instance name")
        self.no_property_change(defn, 'resource_group')
        self.no_property_change(defn, 'storage')
        self.no_location_change(defn)

        self.set_common_state(defn)
        self.copy_mgmt_credentials(defn)
        self.machine_name = defn.machine_name
        self.storage = defn.storage
        self.resource_group = defn.resource_group
        self.location = defn.location

        if not self.public_client_key:
            (private, public) = create_key_pair()
            self.public_client_key = public
            self.private_client_key = private

        if not self.public_host_key:
            host_key_type = "ed25519" if self.state_version != "14.12" and nixops.util.parse_nixos_version(defn.config["nixosRelease"]) >= ["15", "09"] else "ecdsa"
            (private, public) = create_key_pair(type=host_key_type)
            self.public_host_key = public
            self.private_host_key = private

        if check:
            self.check_ip()
            self.check_network_iface()
            vm = self.get_settled_resource()
            if vm:
                if self.vm_id:
                    self.warn_if_failed(vm)
                    self.handle_changed_property('location', normalize_location(vm.location),
                                                 can_fix = False)
                    self.handle_changed_property('size', vm.hardware_profile.virtual_machine_size)
                    # workaround: for some reason the availability set name gets capitalized
                    availability_set = ResId(vm.availability_set_reference and
                                             vm.availability_set_reference.reference_uri)
                    _as_res_name = availability_set.get('resource', None)
                    _as_res_name = _as_res_name.lower() if _as_res_name else None
                    availability_set['resource'] = _as_res_name
                    self.handle_changed_property('availability_set', availability_set.id)
                    self.handle_changed_property('public_ipv4', self.fetch_public_ip())
                    self.handle_changed_property('private_ipv4', self.fetch_private_ip())
                    self.update_ssh_known_hosts()

                    # check the root disk
                    os_disk_res_name = "OS disk of {0}".format(self.full_name)
                    _root_disk_id = find_root_disk(self.block_device_mapping)
                    assert _root_disk_id is not None
                    root_disk = self.block_device_mapping[_root_disk_id]
                    self.warn_if_changed(root_disk["host_caching"], vm.storage_profile.os_disk.caching, "host_caching",
                                         resource_name = os_disk_res_name, can_fix = False)
                    self.warn_if_changed(root_disk["name"], vm.storage_profile.os_disk.name, "name",
                                         resource_name = os_disk_res_name, can_fix = False)
                    self.warn_if_changed(root_disk["media_link"], vm.storage_profile.os_disk.virtual_hard_disk.uri, "media_link",
                                         resource_name = os_disk_res_name, can_fix = False)
                    self.update_block_device_mapping(_root_disk_id, root_disk)

                    # check data disks
                    for d_id, disk in self.block_device_mapping.iteritems():
                        disk_lun = device_name_to_lun(disk['device'])
                        if disk_lun is None: continue
                        vm_disk = next((_vm_disk for _vm_disk in vm.storage_profile.data_disks
                                                 if _vm_disk.virtual_hard_disk.uri == disk['media_link']), None)
                        if vm_disk is not None:
                            disk_res_name = "data disk {0}({1})".format(disk['name'], d_id)
                            disk["host_caching"] = self.warn_if_changed(disk["host_caching"], vm_disk.caching,
                                                                        "host_caching", resource_name = disk_res_name)
                            disk["size"] = self.warn_if_changed(disk["size"], vm_disk.disk_size_gb,
                                                                "size", resource_name = disk_res_name)
                            self.warn_if_changed(disk["name"], vm_disk.name,
                                                 "name", resource_name = disk_res_name, can_fix = False)
                            if disk.get("needs_attach", False):
                                self.warn("disk {0}({1}) was not supposed to be attached".format(disk['name'], d_id))
                                disk["needs_attach"] = False

                            if vm_disk.lun != disk_lun:
                                self.warn("disk {0}({1}) is attached to this instance at a "
                                          "wrong LUN {2} instead of {3}"
                                          .format(disk['name'], disk['media_link'], vm_disk.lun, disk_lun))
                                self.log("detaching disk {0}({1})...".format(disk['name'], disk['media_link']))
                                vm.storage_profile.data_disks.remove(vm_disk)
                                self.cmc().virtual_machines.create_or_update(self.resource_group, vm)
                                disk["needs_attach"] = True
                        else:
                            if not disk.get('needs_attach', False):
                                self.warn("disk {0}({1}) has been unexpectedly detached".format(disk['name'], d_id))
                                disk["needs_attach"] = True
                            if not self.blob_exists(disk['media_link']):
                                self.warn("disk BLOB {0}({1}) has been unexpectedly deleted".format(disk['name'], d_id))
                                disk = None

                        self.update_block_device_mapping(d_id, disk)

                    # detach "unexpected" disks
                    found_unexpected_disks = False
                    for vm_disk in vm.storage_profile.data_disks:
                        state_disk_id = next((_d_id for _d_id, _disk in self.block_device_mapping.iteritems()
                                              if vm_disk.virtual_hard_disk.uri == _disk['media_link']), None)
                        if state_disk_id is None:
                            self.warn("unexpected disk {0}({1}) is attached to this virtual machine"
                                      .format(vm_disk.name, vm_disk.virtual_hard_disk.uri))
                            vm.storage_profile.data_disks.remove(vm_disk)
                            found_unexpected_disks = True
                    if found_unexpected_disks:
                        self.log("detaching unexpected disk(s)...")
                        self.cmc().virtual_machines.create_or_update(self.resource_group, vm)

                else:
                    self.warn_not_supposed_to_exist(valuable_data = True)
                    self.confirm_destroy()
            else:
                if self.vm_id:
                    self.warn("the instance seems to have been destroyed behind our back")
                    if not allow_recreate: raise Exception("use --allow-recreate to fix")
                    self._node_deleted()

        if self.vm_id:
            if defn.availability_set != self.availability_set:
                self.warn("a change of the availability set is requested "
                          "that requires that the virtual machine is re-created")
                if allow_recreate:
                    self.log("destroying the virtual machine, but preserving the disk contents...")
                    self.destroy_resource()
                    self._node_deleted()
                else:
                    raise Exception("use --allow-recreate to fix")

        if self.vm_id and not allow_reboot:
            if defn.size != self.size:
                raise Exception("reboot is required to change the virtual machine size; please run with --allow-reboot")

        self._assert_no_impossible_disk_changes(defn)

        # change the root disk of a deployed vm
        # this is not directly supported by create_or_update API
        if self.vm_id:
            def_root_disk_id = defn_find_root_disk(defn.block_device_mapping)
            assert def_root_disk_id is not None
            def_root_disk = defn.block_device_mapping[def_root_disk_id]
            state_root_disk_id = find_root_disk(self.block_device_mapping)
            assert state_root_disk_id is not None
            state_root_disk = self.block_device_mapping[state_root_disk_id]

            if ( (def_root_disk_id != state_root_disk_id) or
                 (def_root_disk['host_caching'] != state_root_disk['host_caching']) or
                 (def_root_disk['name'] != state_root_disk['name']) ):
                self.warn("a modification of the root disk is requested "
                          "that requires that the virtual machine is re-created")
                if allow_recreate:
                    self.log("destroying the virtual machine, but preserving the disk contents...")
                    self.destroy_resource()
                    self._node_deleted()
                else:
                    raise Exception("use --allow-recreate to fix")

        self._change_existing_disk_parameters(defn)

        if self.public_ip is None and defn.obtain_ip:
            self.log("getting an IP address")
            self.create_or_update_ip(defn)
        if self.public_ip and defn.obtain_ip and self.ip_properties_changed(defn):
            self.log("updating IP address properties")
            self.create_or_update_ip(defn)

        self._create_vm(defn)

        # changing vm properties first because size change may be
        # required before you attach more disks or join a load balancer
        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            vm = self.get_settled_resource_assert_exists()
            vm.hardware_profile = HardwareProfile(virtual_machine_size = defn.size)
            self.cmc().virtual_machines.create_or_update(self.resource_group, vm)
            self.copy_properties(defn)

        self._create_missing_attach_detached(defn)

        self._generate_default_encryption_keys()

        if self.iface_properties_changed(defn):
            self.log("updating network interface properties of {0}...".format(self.full_name))
            #FIXME: handle missing network interface
            iface = self.nrpc().network_interfaces.get(self.resource_group, self.network_interface).network_interface
            self.create_or_update_iface(defn)

        # delete IP address if it is not needed anymore
        if self.public_ip and not self.obtain_ip:
            self.delete_ip_address()


    # change existing disk parameters as much as possible within the technical limitations
    def _change_existing_disk_parameters(self, defn):
        for d_id, disk in defn.block_device_mapping.iteritems():
            state_disk = self.block_device_mapping.get(d_id, None)
            if state_disk is None: continue
            lun = device_name_to_lun(disk['device'])
            if lun is None: continue
            if self.vm_id and not state_disk.get('needs_attach', False):
                if disk['host_caching'] != state_disk['host_caching']:
                    self.log("changing parameters of the attached disk {0}({1})"
                             .format(disk['name'], d_id))
                    vm = self.get_settled_resource_assert_exists()
                    vm_disk = next((_disk for _disk in vm.storage_profile.data_disks
                                         if _disk.virtual_hard_disk.uri == disk['media_link']), None)
                    if vm_disk is None:
                        raise Exception("disk {0}({1}) was supposed to be attached at {2} "
                                        "but wasn't found; please run deploy --check to fix this"
                                        .format(disk['name'], d_id, disk['device']))
                    vm_disk.caching = disk['host_caching']
                    self.cmc().virtual_machines.create_or_update(self.resource_group, vm)
                    state_disk['host_caching'] = disk['host_caching']
            else:
                state_disk['host_caching'] = disk['host_caching']
                state_disk['name'] = disk['name']
                state_disk['device'] = disk['device']
            state_disk['encrypt'] = disk['encrypt']
            state_disk['passphrase'] = disk['passphrase']
            state_disk['is_ephemeral'] = disk['is_ephemeral']
            self.update_block_device_mapping(d_id, state_disk)

    # Certain disk configuration changes can't be deployed in
    # one step such as replacing a disk attached to a particular
    # LUN or reattaching a disk at a different LUN.
    # You can reattach the os disk as a data disk in one step.
    # You can't reattach the data disk as os disk in one step.
    # This is a limitation of the disk modification process,
    # which ensures clean dismounts:
    # new disks are attached, nixos configuration is deployed
    # which mounts new disks and dismounts the disks about to
    # be detached, and only then the disks are detached.
    def _assert_no_impossible_disk_changes(self, defn):
        if self.vm_id is None: return

        for d_id, disk in defn.block_device_mapping.iteritems():
            same_lun_id = next((_id for _id, _d in self.block_device_mapping.iteritems()
                                    if _d['device'] == disk['device']), None)
            disk_lun = device_name_to_lun(disk['device'])
            if same_lun_id is not None and disk_lun is not None and (same_lun_id != d_id) and (
                  not self.block_device_mapping[same_lun_id].get("needs_attach", False) ):
                raise Exception("can't attach Azure disk {0}({1}) because the target LUN {2} is already "
                                "occupied by Azure disk {3}; you need to deploy a configuration "
                                "with this LUN left empty before using it to attach a different data disk"
                                .format(disk['name'], disk["media_link"], disk["device"], same_lun_id))

            state_disk = self.block_device_mapping.get(d_id, None)
            _lun = state_disk and device_name_to_lun(state_disk['device'])
            if state_disk and _lun is not None and not state_disk.get('needs_attach', False):
                if state_disk['device'] != disk['device']:
                    raise Exception("can't reattach Azure disk {0}({1}) to a different LUN in one step; "
                                    "you need to deploy a configuration with this disk detached from {2} "
                                  "before attaching it to {3}"
                                 .format(disk['name'], d_id, state_disk['device'], disk['device']))
                if state_disk['name'] != disk['name']:
                    raise Exception("cannot change the name of the attached disk {0}({1})"
                                    .format(state_disk['name'], d_id))

    # create missing, attach detached disks
    def _create_missing_attach_detached(self, defn):
        for d_id, disk in defn.block_device_mapping.iteritems():
            lun = device_name_to_lun(disk['device'])
            if lun is None: continue
            _disk = self.block_device_mapping.get(d_id, None)
            if _disk and not _disk.get("needs_attach", False): continue

            self.log("attaching data disk {0}({1})".format(disk['name'], d_id))
            vm = self.get_settled_resource_assert_exists()
            vm.storage_profile.data_disks.append(DataDisk(
                name = disk['name'],
                virtual_hard_disk = VirtualHardDisk(uri = disk['media_link']),
                caching = disk['host_caching'],
                create_option = ( DiskCreateOptionTypes.attach
                                  if self.blob_exists(disk['media_link'])
                                  else DiskCreateOptionTypes.empty ),
                lun = lun,
                disk_size_gb = disk['size']
            ))
            self.cmc().virtual_machines.create_or_update(self.resource_group, vm)
            self.update_block_device_mapping(d_id, disk)

    # generate LUKS key if the model didn't specify one
    def _generate_default_encryption_keys(self):
        for d_id, disk in self.block_device_mapping.iteritems():
            if disk.get('encrypt', False) and ( disk.get('passphrase', "") == ""
                                            and self.generated_encryption_keys.get(d_id, None) is None):
                self.log("generating an encryption key for disk {0}({1})"
                         .format(disk['name'], d_id))
                self.update_generated_encryption_keys(d_id, generate_random_string(length=256))


    def copy_iface_properties(self, defn):
        self.backend_address_pools = defn.backend_address_pools
        self.inbound_nat_rules = defn.inbound_nat_rules
        self.obtain_ip = defn.obtain_ip
        self.ip_resid = defn.ip_resid
        self.security_group = defn.security_group
        self.subnet = defn.subnet

    def iface_properties_changed(self, defn):
        return ( self.backend_address_pools != defn.backend_address_pools or
                 self.inbound_nat_rules != defn.inbound_nat_rules or
                 self.obtain_ip != defn.obtain_ip or
                 self.ip_resid != defn.ip_resid or
                 self.security_group != defn.security_group or
                 self.subnet != defn.subnet )

    def create_or_update_iface(self, defn):
        self.nrpc().network_interfaces.create_or_update(
            self.resource_group, self.machine_name,
            NetworkInterface(name = self.machine_name,
                             location = defn.location,
                             network_security_group = defn.security_group and
                                                      ResId(defn.security_group),
                             ip_configurations = [ NetworkInterfaceIpConfiguration(
                                 name = 'default',
                                 private_ip_allocation_method = IpAllocationMethod.dynamic,
                                 subnet = ResId(defn.subnet),
                                 load_balancer_backend_address_pools = [
                                     ResId(pool) for pool in defn.backend_address_pools ],
                                 load_balancer_inbound_nat_rules = [
                                     ResId(rule) for rule in defn.inbound_nat_rules ],
                                 public_ip_address = defn.ip_resid and ResId(defn.ip_resid),
                             )]
                           ))
        self.network_interface = self.machine_name
        self.copy_iface_properties(defn)
        self.public_ipv4 = self.fetch_public_ip()
        if self.public_ipv4:
            self.log("got public IP: {0}".format(self.public_ipv4))
        self.update_ssh_known_hosts()
        self.private_ipv4 = self.fetch_private_ip()
        if self.private_ipv4:
            self.log("got private IP: {0}".format(self.private_ipv4))

    def copy_ip_properties(self, defn):
        self.ip_allocation_method = defn.ip_allocation_method
        self.ip_domain_name_label = defn.ip_domain_name_label

    def ip_properties_changed(self, defn):
        return ( self.ip_allocation_method != defn.ip_allocation_method or
                 self.ip_domain_name_label != defn.ip_domain_name_label )

    def create_or_update_ip(self, defn):
        dns_settings = PublicIpAddressDnsSettings(
                          domain_name_label = defn.ip_domain_name_label,
                       ) if defn.ip_domain_name_label else None
        self.nrpc().public_ip_addresses.create_or_update(
            self.resource_group, self.machine_name,
            PublicIpAddress(
                location = defn.location,
                public_ip_allocation_method = defn.ip_allocation_method,
                dns_settings = dns_settings,
                idle_timeout_in_minutes = 4,
            ))
        self.public_ip = self.machine_name
        self.copy_ip_properties(defn)

    def defn_root_image_url(self, defn):
        # pass thru the full blob url if specified
        if defn.root_disk_image_blob.lower().startswith(('http://', 'https://')):
            return defn.root_disk_image_blob

        # obtain container name from the blob resource if deployed by nixops,
        # otherwise assume it's stored in ephemeral_disk_container
        # Azure requires that the root image and VM blobs are in the
        # same storage, so we assume the blob storage is the same as vm storage
        blob_resource = self.get_resource_state(AzureBLOBState, defn.root_disk_image_blob)
        blob_container = blob_resource and blob_resource.container
        if(blob_resource and blob_resource.get_storage_name() and
                            (blob_resource.get_storage_name() != defn.storage) ):
            raise("root disk image BLOB must reside "
                  "in the same storage as {0} disk BLOBs"
                  .format(self.full_name))
        return("https://{0}.blob.core.windows.net/{1}/{2}"
               .format(defn.storage,
                       blob_container or defn.ephemeral_disk_container,
                       defn.root_disk_image_blob))

    def _create_vm(self, defn):
        if self.network_interface is None:
            self.log("creating a network interface")
            self.create_or_update_iface(defn)

        if self.vm_id: return

        if self.get_settled_resource():
            raise Exception("tried creating a virtual machine that already exists; "
                            "please run 'deploy --check' to fix this")

        root_disk_id = defn_find_root_disk(defn.block_device_mapping)
        assert root_disk_id is not None
        root_disk_spec = defn.block_device_mapping[root_disk_id]
        existing_root_disk = self.block_device_mapping.get(root_disk_id, None)

        self.log("creating {0}...".format(self.full_name))
        nic_id = self.nrpc().network_interfaces.get(
                               self.resource_group, self.network_interface).network_interface.id
        custom_data = ('ssh_host_ecdsa_key=$(cat<<____HERE\n{0}\n____HERE\n)\n'
                       'ssh_host_ecdsa_key_pub="{1}"\nssh_root_auth_key="{2}"\n'
                      ).format(self.private_host_key, self.public_host_key, self.public_client_key)

        data_disks = [ DataDisk(
                           name = disk['name'],
                           virtual_hard_disk = VirtualHardDisk(uri = disk['media_link']),
                           caching = disk['host_caching'],
                           create_option = ( DiskCreateOptionTypes.attach
                                             if self.blob_exists(disk['media_link'])
                                             else DiskCreateOptionTypes.empty ),
                           lun = device_name_to_lun(disk['device']),
                           disk_size_gb = disk['size']
                           )
                       for disk_id, disk in defn.block_device_mapping.iteritems()
                       if device_name_to_lun(disk['device']) is not None ]

        root_disk_exists = self.blob_exists(root_disk_spec['media_link'])

        req = self.cmc().virtual_machines.begin_creating_or_updating(
            self.resource_group,
            VirtualMachine(
                location = self.location,
                name = self.machine_name,
                os_profile = ( None
                               if root_disk_exists
                               else OSProfile(
                                   admin_username="randomuser",
                                   admin_password="aA9+" + generate_random_string(length=32),
                                   computer_name=self.machine_name,
                                   custom_data = base64.b64encode(custom_data)
                             ) ),
                availability_set_reference = defn.availability_set and ResId(defn.availability_set),
                hardware_profile = HardwareProfile(virtual_machine_size = defn.size),
                network_profile = NetworkProfile(
                    network_interfaces = [
                        NetworkInterfaceReference(reference_uri = nic_id)
                    ],
                ),
                storage_profile = StorageProfile(
                    os_disk = OSDisk(
                        caching = root_disk_spec['host_caching'],
                        create_option = ( DiskCreateOptionTypes.attach
                                          if root_disk_exists
                                          else DiskCreateOptionTypes.from_image),
                        name = root_disk_spec['name'],
                        virtual_hard_disk = VirtualHardDisk(uri = root_disk_spec['media_link']),
                        source_image = (None
                                        if root_disk_exists
                                        else VirtualHardDisk(uri = self.defn_root_image_url(defn)) ),
                        operating_system_type = "Linux"
                    ),
                    data_disks = data_disks
                )
            )
        )
        print req.__dict__

        # we take a shortcut: wait for either provisioning to fail or for public ip to get assigned
        def check_req():
            return ((self.fetch_public_ip() is not None)
                 or (self.cmc().get_long_running_operation_status(req.azure_async_operation).status
                        != ComputeOperationStatus.in_progress))
        check_wait(check_req, initial=1, max_tries=500, exception=True)

        req_status = self.cmc().get_long_running_operation_status(req.azure_async_operation)
        if req_status.status == ComputeOperationStatus.failed:
            raise Exception('failed to provision {0}; {1}'
                        .format(self.full_name, req_status.error.__dict__))

        self.vm_id = self.machine_name
        self.state = self.STARTING
        self.ssh_pinged = False
        self.copy_properties(defn)

        self.public_ipv4 = self.fetch_public_ip()
        if self.public_ipv4:
            self.log("got public IP: {0}".format(self.public_ipv4)) 
        self.update_ssh_known_hosts()
        self.private_ipv4 = self.fetch_private_ip()
        if self.private_ipv4:
            self.log("got private IP: {0}".format(self.private_ipv4))

        for d_id, disk in defn.block_device_mapping.iteritems():
            self.update_block_device_mapping(d_id, disk)


    def after_activation(self, defn):
        # detach the volumes that are no longer in the deployment spec
        for d_id, disk in self.block_device_mapping.items():
            lun = device_name_to_lun(disk['device'])
            if d_id not in defn.block_device_mapping:

                if not disk.get('needs_attach', False) and lun is not None:
                    if disk.get('encrypt', False):
                        dm = "/dev/mapper/{0}".format(disk['name'])
                        self.log("unmounting device '{0}'...".format(dm))
                        # umount with -l flag in case if the regular umount run by activation failed
                        self.run_command("umount -l {0}".format(dm), check=False)
                        self.run_command("cryptsetup luksClose {0}".format(dm), check=False)
                    else:
                        self.log("unmounting device '{0}'...".format(disk['device']))
                        self.run_command("umount -l {0}".format(disk['device']), check=False)

                    self.log("detaching Azure disk {0}({1})...".format(disk['name'], d_id))
                    vm = self.get_settled_resource_assert_exists()
                    vm.storage_profile.data_disks = [
                        _disk
                        for _disk in vm.storage_profile.data_disks
                        if _disk.virtual_hard_disk.uri != disk['media_link'] ]
                    self.cmc().virtual_machines.create_or_update(self.resource_group, vm)
                    disk['needs_attach'] = True
                    self.update_block_device_mapping(d_id, disk)

                if disk['is_ephemeral']:
                    self._delete_volume(disk['media_link'], disk_name = disk['name'])

                # rescan the disk device, to make its device node disappear on older kernels
                self.run_command("sg_scan {0}".format(disk['device']), check=False)

                self.update_block_device_mapping(d_id, None)
                self._delete_encryption_key(d_id)


    def reboot(self, hard=False):
        if hard:
            self.log("sending hard reset to Azure machine...")
            self.cmc().virtual_machines.restart(self.resource_group, self.machine_name)
            self.state = self.STARTING
            self.ssh.reset()
        else:
            MachineState.reboot(self, hard=hard)
        self.ssh_pinged = False

    def start(self):
        if self.vm_id:
            self.state = self.STARTING
            self.log("starting Azure machine...")
            self.cmc().virtual_machines.start(self.resource_group, self.machine_name)

            if self.fetch_private_ip() != self.private_ipv4 or self.fetch_public_ip() != self.public_ipv4:
                self.warn("IP address has changed, you may need to run 'nixops deploy'")

            self.wait_for_ssh(check=True)
            self.send_keys()

    def stop(self):
        if self.vm_id:
           #FIXME: there's also "stopped deallocated" version of this. how to integrate?
            self.log("stopping Azure machine... ")
            self.state = self.STOPPING
            self.cmc().virtual_machines.power_off(self.resource_group, self.machine_name)
            self.state = self.STOPPED
            self.ssh.reset()
            self.ssh_pinged = False

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
        for d_id, disk in self.block_device_mapping.items():
            if disk['is_ephemeral']:
                self._delete_volume(disk['media_link'], disk_name = disk['name'])
            self.update_block_device_mapping(d_id, None)
            self._delete_encryption_key(d_id)

        if self.network_interface:
            self.log("destroying the network interface...")
            try:
                self.nrpc().network_interfaces.get(self.resource_group, self.network_interface)
                self.nrpc().network_interfaces.delete(self.resource_group, self.network_interface)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("seems to have been destroyed already")
            self.network_interface = None

        self.delete_ip_address()

        if self.generated_encryption_keys != {}:
            if not self.depl.logger.confirm("{0} resource still stores generated encryption keys for disks {1}; "
                                            "if the resource is deleted, the keys are deleted along with it "
                                            "and the data will be lost even if you have a copy of the disks' "
                                            "contents; are you sure you want to delete the encryption keys?"
                                            .format(self.full_name, self.generated_encryption_keys.keys()) ):
                raise Exception("cannot continue")
        return True


    def backup(self, defn, backup_id, devices=[]):
        self.log("backing up {0} using ID '{1}'".format(self.full_name, backup_id))

        if sorted(defn.block_device_mapping.keys()) != sorted(self.block_device_mapping.keys()):
            self.warn("the list of disks currently deployed doesn't match the current deployment"
                     " specification; consider running 'deploy' first; the backup may be incomplete")

        backup = {}
        _backups = self.backups
        for d_id, disk in self.block_device_mapping.iteritems():
            media_link = disk['media_link']
            if devices == [] or media_link in devices or disk['name'] in devices or disk['device'] in devices:
                self.log("snapshotting the BLOB {0} backing the Azure disk {1}"
                         .format(media_link, disk['name']))
                blob = parse_blob_url(media_link)
                if blob is None:
                    raise Exception("failed to parse BLOB URL {0}"
                                    .format(media_link))
                if blob['storage'] != self.storage:
                    raise Exception("storage {0} provided in the deployment specification "
                                    "doesn't match the storage of BLOB {1}"
                                    .format(self.storage, media_link))
                snapshot = self.bs().snapshot_blob(blob['container'], blob['name'],
                                                   x_ms_meta_name_values = {
                                                       'nixops_backup_id': backup_id,
                                                       'description': "backup of disk {0} attached to {1}"
                                                                      .format(disk['name'], self.machine_name)
                                                   })
                backup[media_link] = snapshot['x-ms-snapshot']
            _backups[backup_id] = backup
            self.backups = _backups

    def restore(self, defn, backup_id, devices=[]):
        self.log("restoring {0} to backup '{1}'".format(self.full_name, backup_id))

        if self.vm_id:
            self.stop()
            self.log("temporarily deprovisioning {0}".format(self.full_name))
            self.destroy_resource()
            self._node_deleted()

        for d_id, disk in self.block_device_mapping.items():
            media_link = disk['media_link']
            s_id = self.backups[backup_id].get(media_link, None)
            if s_id and (devices == [] or media_link in devices or
                         disk['name'] in devices or disk['device'] in devices):
                blob = parse_blob_url(media_link)
                if blob is None:
                    self.warn("failed to parse BLOB URL {0}; skipping"
                              .format(media_link))
                    continue
                if blob["storage"] != self.storage:
                    raise Exception("storage {0} provided in the deployment specification "
                                    "doesn't match the storage of BLOB {1}"
                                    .format(self.storage, media_link))
                try:
                    self.bs().get_blob_properties(
                            blob["container"], "{0}?snapshot={1}"
                                                .format(blob["name"], s_id))
                except azure.common.AzureMissingResourceHttpError:
                    self.warn("snapshot {0} for disk {1} is missing; skipping".format(s_id, d_id))
                    continue

                self.log("restoring BLOB {0} from snapshot"
                         .format(media_link, s_id))
                self.bs().copy_blob(blob["container"], blob["name"],
                                   "{0}?snapshot={1}"
                                   .format(media_link, s_id) )

        # restore the currently deployed configuration(defn = self)
        self._create_vm(self)


    def remove_backup(self, backup_id, keep_physical=False):
        self.log('removing backup {0}'.format(backup_id))
        _backups = self.backups

        if not backup_id in _backups.keys():
            self.warn('backup {0} not found; skipping'.format(backup_id))
        else:
            for blob_url, snapshot_id in _backups[backup_id].iteritems():
                try:
                    self.log('removing snapshot {0} of BLOB {1}'.format(snapshot_id, blob_url))
                    blob = parse_blob_url(blob_url)
                    if blob is None:
                        self.warn("failed to parse BLOB URL {0}; skipping".format(blob_url))
                        continue
                    if blob["storage"] != self.storage:
                        raise Exception("storage {0} provided in the deployment specification "
                                        "doesn't match the storage of BLOB {1}"
                                        .format(self.storage, blob_url))

                    self.bs().delete_blob(blob["container"], blob["name"], snapshot_id)
                except azure.common.AzureMissingResourceHttpError:
                    self.warn('snapshot {0} of BLOB {1} does not exist; skipping'
                              .format(snapshot_id, blob_url))

            _backups.pop(backup_id)
            self.backups = _backups

    def get_backups(self):
        backups = {}
        for b_id, snapshots in self.backups.iteritems():
            backups[b_id] = {}
            backup_status = "complete"
            info = []
            processed = set()
            for d_id, disk in self.block_device_mapping.items():
                media_link = disk['media_link']
                if not media_link in snapshots.keys():
                    backup_status = "incomplete"
                    info.append("{0} - {1} - not available in backup"
                                .format(self.name, d_id))
                else:
                    snapshot_id = snapshots[media_link]
                    processed.add(media_link)
                    blob = parse_blob_url(media_link)
                    if blob is None:
                        info.append("failed to parse BLOB URL {0}"
                                    .format(media_link))
                        backup_status = "unavailable"
                    elif blob["storage"] != self.storage:
                        info.append("storage {0} provided in the deployment specification "
                                    "doesn't match the storage of BLOB {1}"
                                    .format(self.storage, media_link))
                        backup_status = "unavailable"
                    else:
                        try:
                            snapshot = self.bs().get_blob_properties(
                                            blob["container"], "{0}?snapshot={1}"
                                                               .format(blob["name"], snapshot_id))
                        except azure.common.AzureMissingResourceHttpError:
                            info.append("{0} - {1} - {2} - snapshot has disappeared"
                                        .format(self.name, d_id, snapshot_id))
                            backup_status = "unavailable"

            for media_link in (set(snapshots.keys())-processed):
                info.append("{0} - {1} - {2} - a snapshot of a disk that is not or no longer deployed"
                            .format(self.name, media_link, snapshots[media_link]))
            backups[b_id]['status'] = backup_status
            backups[b_id]['info'] = info

        return backups


    def _check(self, res):
        if(self.subscription_id is None or self.authority_url is None or
           self.user is None or self.password is None):
            res.exists = False
            res.is_up = False
            self.state = self.MISSING;
            return

        vm = self.get_resource()
        if vm is None:
            res.exists = False
            res.is_up = False
            self.state = self.MISSING;
        else:
            res.exists = True

            res.is_up = vm.provisioning_state in [ ProvisioningStateTypes.succeeded,
                                                   ProvisioningStateTypes.creating ]
            if vm.provisioning_state == ProvisioningStateTypes.failed:
                res.messages.append("vm resource exists, but is in a failed state")
            if not res.is_up: self.state = self.STOPPED
            if res.is_up:
                # check that all disks are attached
                res.disks_ok = True
                for d_id, disk in self.block_device_mapping.iteritems():
                    if device_name_to_lun(disk['device']) is None:
                        if vm.storage_profile.os_disk.virtual_hard_disk.uri != disk['media_link']:
                            res.disks_ok = False
                            res.messages.append("different root disk instead of {0}".format(d_id))
                        else: continue
                    if all(disk['media_link'] != d.virtual_hard_disk.uri
                           for d in vm.storage_profile.data_disks):
                        res.disks_ok = False
                        res.messages.append("disk {0}({1}) is detached".format(disk['name'], d_id))
                        if not self.blob_exists(disk['media_link']):
                            res.messages.append("disk {0}({1}) is destroyed".format(disk['name'], d_id))

                self.handle_changed_property('public_ipv4', self.fetch_public_ip())
                self.update_ssh_known_hosts()
                self.handle_changed_property('private_ipv4', self.fetch_private_ip())

                MachineState._check(self, res)

    def get_physical_spec(self):
        block_device_mapping = {
            disk["device"] : {
                'passphrase': Call(RawValue("pkgs.lib.mkOverride 10"),
                                   self.generated_encryption_keys[d_id])
            }
            for d_id, disk in self.block_device_mapping.items()
            if (disk.get('encrypt', False)
                and disk.get('passphrase', "") == ""
                and self.generated_encryption_keys.get(d_id, None) is not None)
        }
        return {
            'require': [
                RawValue("<nixpkgs/nixos/modules/virtualisation/azure-common.nix>")
            ],
            ('deployment', 'azure', 'blockDeviceMapping'): block_device_mapping,
        }

    def get_keys(self):
        keys = MachineState.get_keys(self)
        # Ugly: we have to add the generated keys because they're not
        # there in the first evaluation (though they are present in
        # the final nix-build).
        for d_id, disk in self.block_device_mapping.items():
            if disk.get('encrypt', False) and ( disk.get('passphrase', "") == ""
                                            and self.generated_encryption_keys.get(d_id, None) is not None):
                key_name = disk['name']
                keys["luks-" + key_name] = {
                    'text': self.generated_encryption_keys[d_id],
                    'keyFile': '/run/keys/'+ "luks-" + key_name,
                    'destDir': '/run/keys/',
                    'group': 'root',
                    'permissions': '0600',
                    'user': 'root'
                }
        return keys


    def create_after(self, resources, defn):
        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState) or
                     isinstance(r, AzureBLOBState) or isinstance(r, AzureResourceGroupState) or
                     isinstance(r, AzureVirtualNetworkState) or isinstance(r, AzureAvailabilitySetState) or
                     isinstance(r, AzureDirectoryState) or isinstance(r, AzureFileState) or
                     isinstance(r, AzureLoadBalancerState) or isinstance(r, AzureQueueState) or
                     isinstance(r, AzureReservedIPAddressState) or isinstance(r, AzureShareState) or
                     isinstance(r, AzureTableState) or isinstance(r, AzureNetworkSecurityGroupState) }

    def find_lb_endpoint(self):
        for _inr in self.inbound_nat_rules:
            inr = ResId(_inr)
            lb = self.get_resource_state(AzureLoadBalancerState, inr.get('resource', None))

            nat_rule = lb.inbound_nat_rules.get(inr.get('subresource', None), None)
            if not nat_rule: continue
            if nat_rule.get('backend_port', None) != super(AzureState, self).ssh_port: continue
            port = nat_rule.get('frontend_port', None)

            iface_name = ResId(nat_rule.get('frontend_interface', None)).get('subresource', None)
            if not iface_name: continue
            iface = lb.frontend_interfaces.get(iface_name, None)
            if not iface: continue

            ip_id = ResId(iface.get('public_ip_address', None))
            ip_resource = self.get_resource_state(AzureReservedIPAddressState, ip_id.get('resource', None))
            if not ip_resource: continue
            ip = ip_resource.ip_address

            if ip and port:
                return { 'ip': ip, 'port': port }
        return None

    # return ssh host and port formatted for ssh/known_hosts file
    def get_ssh_host_port(self):
        if self.use_private_ip_address:
            if self.private_ipv4:
                return self.private_ipv4
            else:
                return None
        else:
            if self.public_ipv4:
                return self.public_ipv4
            ep = self.find_lb_endpoint() or {}
            ip = ep.get('ip', None)
            port = ep.get('port', None)
            if ip is not None and port is not None:
                return "[{0}]:{1}".format(ip, port)
            else:
                return None

    @MachineState.ssh_port.getter
    def ssh_port(self):
        if self.public_ipv4 or self.private_ipv4:
            return super(AzureState, self).ssh_port
        else:
            return (self.find_lb_endpoint() or {}).get('port', None)


    def update_ssh_known_hosts(self):
        if self.known_ssh_host_port:
            known_hosts.remove(self.known_ssh_host_port, self.public_host_key)
            self.known_ssh_host_port = None

        ssh_host_port = self.get_ssh_host_port()
        if ssh_host_port:
            known_hosts.add(ssh_host_port, self.public_host_key)
            self.known_ssh_host_port = ssh_host_port

    def get_ssh_name(self):
        ip = self.private_ipv4 if self.use_private_ip_address else self.public_ipv4 or (self.find_lb_endpoint() or {}).get('ip', None)
        if ip is None:
            raise Exception("{0} does not have a routable IPv4 address and is not reachable "
                            "via an inbound NAT rule on a load balancer"
                            .format(self.full_name))
        return ip

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or (self.private_client_key and self.write_ssh_private_key(self.private_client_key))

    def get_ssh_flags(self, scp=False):
        return [ "-i", self.get_ssh_private_key_file() ] + super(AzureState, self).get_ssh_flags(scp = scp)
