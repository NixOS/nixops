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
from azure.servicemanagement import *
from azure.servicemanagement._serialization import _XmlSerializer

import nixops
from nixops import known_hosts
from nixops.util import wait_for_tcp_port, ping_tcp_port
from nixops.util import attr_property, create_key_pair, generate_random_string, check_wait
from nixops.nix_expr import Function, RawValue

from nixops.backends import MachineDefinition, MachineState
from nixops.azure_common import ResourceDefinition, ResourceState

from xml.etree import ElementTree

from azure.mgmt.network import PublicIpAddress, NetworkInterface, NetworkInterfaceIpConfiguration, IpAllocationMethod, ResourceId
from azure.mgmt.compute import *

def device_name_to_lun(device):
    match = re.match(r'/dev/disk/by-lun/(\d+)$', device)
    return  None if match is None or int(match.group(1))>31 else int(match.group(1) )

def lun_to_device_name(lun):
    return ('/dev/disk/by-lun/' + str(lun))

def find_root_disk(block_device_mapping):
   return next((d_id for d_id, d in block_device_mapping.iteritems()
                  if d['device'] == '/dev/sda'), None)


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
        self.authority_url = self.copy_option(x, 'authority', str, empty = True, optional = True)
        self.copy_option(x, 'user', str, empty = True, optional = True)
        self.copy_option(x, 'password', str, empty = True, optional = True)

        self.copy_option(x, 'size', str, empty = False)
        self.copy_option(x, 'location', str, empty = False)
        self.copy_option(x, 'storage', 'resource')
        self.copy_option(x, 'virtualNetwork', 'resource')
        self.copy_option(x, 'resourceGroup', 'resource')

        self.copy_option(x, 'rootDiskImageUrl', str, empty = False)
        self.copy_option(x, 'baseEphemeralDiskUrl', str, optional = True)

        self.obtain_ip = self.get_option_value(x, 'obtainIP', bool)
        self.copy_option(x, 'availabilitySet', str)

        def opt_disk_name(dname):
            return ("{0}-{1}".format(self.machine_name, dname) if dname is not None else None)

        def parse_block_device(xml):
            disk_name = self.get_option_value(xml, 'name', str)

            media_link = self.get_option_value(xml, 'mediaLink', str, optional = True)
            if not media_link and self.base_ephemeral_disk_url:
                media_link = "{0}{1}-{2}.vhd".format(self.base_ephemeral_disk_url,
                                                self.machine_name, disk_name)
            if not media_link:
                raise Exception("{0}: ephemeral disk {1} must specify mediaLink"
                                .format(self.machine_name, disk_name))
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

        self.block_device_mapping = { parse_block_device(d)['media_link']: parse_block_device(d)
                                      for d in x.findall("attr[@name='blockDeviceMapping']/attrs/attr") }

        for d_id, disk in self.block_device_mapping.iteritems():
            if disk['device'] != "/dev/sda" and device_name_to_lun(disk['device']) is None:
                raise Exception("{0}: blockDeviceMapping only supports /dev/sda and "
                                "/dev/disk/by-lun/X block devices, where X is in 0..31 range"
                                .format(self.machine_name))
        if find_root_disk(self.block_device_mapping) is None:
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

    size = attr_property("azure.size", None)
    location = attr_property("azure.location", None)

    public_client_key = attr_property("azure.publicClientKey", None)
    private_client_key = attr_property("azure.privateClientKey", None)

    public_host_key = attr_property("azure.publicHostKey", None)
    private_host_key = attr_property("azure.privateHostKey", None)

    storage = attr_property("azure.storage", None)
    virtual_network = attr_property("azure.virtualNetwork", None)
    resource_group = attr_property("azure.resourceGroup", None)

    obtain_ip = attr_property("azure.obtainIP", None, bool)
    availability_set = attr_property("azure.availabilitySet", None)

    block_device_mapping = attr_property("azure.blockDeviceMapping", {}, 'json')
    generated_encryption_keys = attr_property("azure.generatedEncryptionKeys", {}, 'json')

    backups = attr_property("azure.backups", {}, 'json')

    public_ip = attr_property("azure.publicIP", None)
    network_interface = attr_property("azure.networkInterface", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        ResourceState.__init__(self, depl, name, id)
        self._sms = None
        self._bs = None

    @property
    def resource_id(self):
        return self.machine_name

    def show_type(self):
        s = super(AzureState, self).show_type()
        return "{0} [{1}; {2}]".format(s, self.location or "???", self.size or "???")

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

    # API calls throw 'conflict' if they involve disks whose
    # attached_to property is not (yet) None,
    # a condition that may persist for several seconds after
    # delete_data_disk and similar requests finish
    def _wait_disk_detached(self, volume_id, disk_id = None):
        self.log("waiting for Azure disk {0} to detach..."
                 .format(disk_id or volume_id))

        def check_detached():
            return self.sms().get_disk(volume_id).attached_to is None
        check_wait(check_detached, initial=1, max_tries=100, exception=True)

    # delete_vhd = None: ask the user
    def _delete_volume(self, media_link, disk_id = None, delete_vhd = None):
        if media_link is None:
            self.warn("attempted to delete a disk without a BLOB URL; this is a bug")
            return
        try:
            #self._wait_disk_detached(volume_id, disk_id = disk_id)

            if delete_vhd or (delete_vhd is None and
                              self.depl.logger.confirm("are you sure you want to destroy "
                                                       "the contents(BLOB) of Azure disk '{0}'?"
                                                       .format(disk_id or media_link)) ):
                self.log("destroying Azure disk BLOB '{0}'...".format(media_link))
                blob = self.parse_blob_url(media_link)
                if blob is None:
                    raise Exception("failed to parse BLOB URL {0}".format(media_link))
                if blob["storage"] != self.storage:
                    raise Exception("storage {1} provided in the deployment specification "
                                    "doesn't match the storage of BLOB {1}"
                                    .format(self.storage, media_link))
                self.bs().delete_blob(blob["container"], blob["name"])
            else:
                self.log("keeping the Azure disk BLOB '{0}'...".format(disk_id or media_link))

        except azure.common.AzureMissingResourceHttpError:
            self.warn("seems to have been destroyed already")

    def blob_exists(self, media_link):
        try:
            blob = self.parse_blob_url(media_link)
            if blob["storage"] != self.storage:
                raise Exception("storage {1} provided in the deployment specification "
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
        ssh_host_port = self.get_ssh_host_port()
        if ssh_host_port and self.public_host_key:
            known_hosts.remove(ssh_host_port, self.public_host_key)
        self.public_ipv4 = None


    defn_properties = [ 'size', 'obtain_ip', 'availability_set' ]

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
        req = self.cmc().virtual_machines.delete(self.resource_group, self.resource_id)

    def is_settled(self, resource):
        return True

    def fetch_PIP(self):
        d = self.sms().get_deployment_by_name(self.hosted_service, self.deployment)
        instance = next((r for r in d.role_instance_list if r.instance_name == self.machine_name), None)
        return (instance and instance.public_ips and instance.public_ips[0].address)

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


    deployment_locks = {}
    master_lock = threading.Lock()

    @property
    def deployment_lock(self):
        with self.master_lock:
            lock_name = "{0}###{1}".format(self.hosted_service, self.deployment)
            if lock_name not in self.deployment_locks:
                self.deployment_locks[lock_name] = threading.Lock()
            return self.deployment_locks[lock_name]


    def create(self, defn, check, allow_reboot, allow_recreate):
        self.no_change(self.machine_name != defn.machine_name, "instance name")
        self.no_property_change(defn, 'resource_group')
        self.no_property_change(defn, 'virtual_network')
        self.no_property_change(defn, 'location')

        self.set_common_state(defn)
        self.copy_mgmt_credentials(defn)
        self.machine_name = defn.machine_name
        self.storage = defn.storage
        self.resource_group = defn.resource_group
        self.virtual_network = defn.virtual_network
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
            vm = self.get_settled_resource()
            if vm:
                if self.vm_id:
                    self.handle_changed_property('size', vm.hardware_profile.virtual_machine_size)
                    public_ipv4 = self.nrpc().public_ip_addresses.get(
                                      self.resource_group, self.public_ip).public_ip_address.ip_address
                    self.handle_changed_property('public_ipv4', public_ipv4)
                    self.update_ssh_known_hosts()
                else:
                    self.warn_not_supposed_to_exist(valuable_data = True)
                    self.confirm_destroy()
            else:
                if self.vm_id:
                    self.warn("the instance seems to have been destroyed behind our back")
                    if not allow_recreate: raise Exception("use --allow-recreate to fix")
                    self._node_deleted()

        if self.vm_id and not allow_reboot:
            if defn.size != self.size:
                raise Exception("reboot is required to change the virtual machine size; please run with --allow-reboot")
            if defn.availability_set != self.availability_set:
                raise Exception("reboot is required to change the availability set name; please run with --allow-reboot")

        self._assert_no_impossible_disk_changes(defn)

        # change the root disk of a deployed vm
        # FIXME: implement this better via update_role?
        #if self.vm_id:
            #def_root_disk_id = find_root_disk(defn.block_device_mapping)
            #assert def_root_disk_id is not None
            #def_root_disk = defn.block_device_mapping[def_root_disk_id]
            #self_root_disk_id = find_root_disk(self.block_device_mapping)
            #assert self_root_disk_id is not None
            #self_root_disk = self.block_device_mapping[self_root_disk_id]

            #if ( (def_root_disk_id != def_root_disk_id) or
                 #(def_root_disk["ephemeral"] != self_root_disk["ephemeral"]) or
                 #(def_root_disk["host_caching"] != self_root_disk["host_caching"]) or
                 #(def_root_disk["label"] != self_root_disk["label"]) ):
                #self.warn("modification of the root disk of {0} is requested, "
                          #"which requires that the machine is re-created"
                          #.format(self.full_name))
                #if allow_recreate:
                    #self.destroy_resource()
                    #self._node_deleted()
                #else:
                    #raise Exception("use --allow-recreate to fix")

        #self._change_existing_disk_parameters(defn)

        #self._create_ephemeral_disks_from_blobs(defn)

        self._create_vm(defn)

        #self._attach_detached_disks(defn)
        #self._create_missing_attach_new(defn)

        self._generate_default_encryption_keys()

        if self.properties_changed(defn):
            self.log("updating properties of {0}...".format(self.full_name))
            vm = self.get_settled_resource()
            if not vm:
                raise Exception("{0} has been deleted behind our back; "
                                "please run 'deploy --check' to fix this"
                                .format(self.full_name))
            vm.hardware_profile = HardwareProfile(virtual_machine_size = defn.size)
            self.cmc().virtual_machines.create_or_update(self.resource_group, vm)
            self.copy_properties(defn)


    # change existing disk params as much as possible within the technical limitations
    def _change_existing_disk_parameters(self, defn):
        for d_id, disk in defn.block_device_mapping.iteritems():
            curr_disk = self.block_device_mapping.get(d_id, None)
            if curr_disk is None: continue
            lun = device_name_to_lun(disk["device"])
            if lun is None: continue
            if self.vm_id and not curr_disk.get("needs_attach", False):
                if disk["device"] != curr_disk["device"]:
                    raise Exception("can't change LUN of the attached disk {0}; "
                                    "please deploy a configuration with this disk detached first".format(d_id))
                # update_data_disk seems to allow the label change, but it does nothing
                if disk["label"] != curr_disk["label"]: #FIXME: recreate vm for this?
                    raise Exception("can't change the label of the attached disk {0}".format(d_id))
                if disk["host_caching"] != curr_disk["host_caching"]:
                    self.log("changing parameters of the attached disk {0}".format(d_id))
                    req = self.sms().update_data_disk(self.hosted_service, self.deployment, self.machine_name,
                                                      lun, updated_lun = lun, 
                                                      disk_name = curr_disk["name"],
                                                      host_caching = disk["host_caching"] )
                    self.finish_request(req)
            curr_disk["device"] = disk["device"]
            curr_disk["host_caching"] = disk["host_caching"]
            curr_disk["label"] = disk["label"]
            curr_disk["passphrase"] = disk["passphrase"]
            self.update_block_device_mapping(d_id, curr_disk)

    # check that we aren't making impossible changes like
    # changing LUN, ephemeral, media_link for ephemeral disks
    def _assert_no_impossible_disk_changes(self, defn):
        if self.vm_id is None: return

        for d_id, disk in defn.block_device_mapping.iteritems():
            same_lun_id = next((_id for _id, d in self.block_device_mapping.iteritems()
                                    if d["device"] == disk["device"]), None)
            if same_lun_id is not None and (same_lun_id != d_id) and (
                not self.block_device_mapping[same_lun_id].get("needs_attach", False) ):
                raise Exception("can't mount Azure disk '{0}' because its LUN({1}) is already "
                                "occupied by Azure disk '{2}'; you need to deploy a configuration "
                                "with this LUN left empty before using it to attach a different data disk"
                                .format(d_id, disk["device"], same_lun_id))

    # attach existing but detached disks
    def _attach_detached_disks(self, defn):
        for d_id, _disk in defn.block_device_mapping.iteritems():
            disk = self.block_device_mapping.get(d_id, None)
            if disk is None or not disk.get("needs_attach", False): continue
            lun = device_name_to_lun(disk["device"])
            if lun is not None:
                with self.deployment_lock:
                    self.log("attaching data disk {0} to {1}"
                            .format(d_id, self.full_name))
                    req = self.sms().add_data_disk(
                            self.hosted_service, self.deployment, self.machine_name,
                            lun, disk_name = disk['name'],
                            host_caching = _disk['host_caching'],
                            disk_label = _disk['label'] )
                    self.finish_request(req)
                disk["needs_attach"] = False
                disk["host_caching"] = _disk["host_caching"]
                disk["label"] = _disk["label"]
                self.update_block_device_mapping(d_id, disk)

    # create missing disks/attach new external disks
    # creation code assumes that the blob doesn't exist because
    # otherwise a disk would be created from it by _create_ephemeral_disks_from_blobs()
    def _create_missing_attach_new(self, defn):
        for d_id, disk in defn.block_device_mapping.iteritems():
            if d_id in self.block_device_mapping: continue
            with self.deployment_lock:
                self.log("attaching data disk {0} to {1}"
                        .format(d_id, self.full_name))
                if disk["ephemeral"]:
                    req = self.sms().add_data_disk(
                              defn.hosted_service, defn.deployment, defn.machine_name,
                              device_name_to_lun(disk['device']),
                              host_caching = disk['host_caching'],
                              media_link = disk['media_link'],
                              disk_label = disk['label'],
                              logical_disk_size_in_gb = disk['size']
                          )
                    self.finish_request(req)
                    dd = self.sms().get_data_disk(defn.hosted_service, defn.deployment, defn.machine_name,
                                                  device_name_to_lun(disk['device']))
                    disk['name'] = dd.disk_name
                else:
                    req = self.sms().add_data_disk(
                              defn.hosted_service, defn.deployment, defn.machine_name,
                              device_name_to_lun(disk['device']),
                              disk_name = disk['name'],
                              host_caching = disk['host_caching'],
                              disk_label = disk['label']
                          )
                    self.finish_request(req)

            self.update_block_device_mapping(d_id, disk)

    # generate LUKS key if the model didn't specify one
    def _generate_default_encryption_keys(self):
        for d_id, disk in self.block_device_mapping.iteritems():
            if disk.get('encrypt', False) and ( disk.get('passphrase', "") == ""
                                            and self.generated_encryption_keys.get(d_id, None) is None):
                self.log("generating an encryption key for disk {0}".format(d_id))
                self.update_generated_encryption_keys(d_id, generate_random_string(length=256))

    # This is an ugly hack around the fact that to create a new disk,
    # add_data_disk() needs to be called in a different way depending
    # on whether the blob exists and there's no API to check direcly
    # whether the blob exists or not.
    # We work around it by attempting to create a disk from the blob instead
    # of relying on add_data_disk(), and use add_data_disk() only to create
    # new blobs(for which there's no other API) and attaching existing disks.
    # The same problem and solution applies to the root disk.
    def _create_ephemeral_disks_from_blobs(self, defn):
        for d_id, disk in defn.block_device_mapping.iteritems():
            if d_id in self.block_device_mapping or not disk["ephemeral"]: continue
            try:
                new_name = "nixops-{0}-{1}-{2}".format(self.machine_name, disk["ephemeral_name"],
                                                        random.randrange(1000000000))
                self.log("attempting to create a disk resource for {0}".format(d_id))
                self._create_disk(device_name_to_lun(disk["device"]) is None,
                                  disk["label"], disk["media_link"],
                                  new_name, "Linux")
                new_disk = disk.copy()
                new_disk["name"] = new_name
                new_disk["needs_attach"] = True
                self.update_block_device_mapping(d_id, new_disk)

            except azure.common.AzureMissingResourceHttpError:
                self.warn("looks like the underlying blob doesn't exist, so it will be created later")
            except azure.common.AzureConflictHttpError:
                self.warn("got ConflictError which most likely means that the blob "
                          "exists and is being used by another disk resource")


    def _create_vm(self, defn):
        if self.public_ip is None and defn.obtain_ip:
            self.log("getting an IP address")
            self.nrpc().public_ip_addresses.create_or_update(
                self.resource_group, self.machine_name,
                PublicIpAddress(
                    location = defn.location,
                    public_ip_allocation_method = 'Dynamic',
                    idle_timeout_in_minutes = 4,
                ))
            self.public_ip = self.machine_name
            self.obtain_ip = defn.obtain_ip

        if self.network_interface is None:
            self.log("creating a network interface")
            public_ip_id = self.nrpc().public_ip_addresses.get(
                               self.resource_group, self.public_ip).public_ip_address.id

            subnet = self.nrpc().subnets.get(self.resource_group, self.virtual_network, self.virtual_network).subnet
            self.nrpc().network_interfaces.create_or_update(
                self.resource_group, self.machine_name,
                NetworkInterface(name = self.machine_name,
                                 location = defn.location,
                                 ip_configurations = [ NetworkInterfaceIpConfiguration(
                                     name='default',
                                     private_ip_allocation_method = IpAllocationMethod.dynamic,
                                     subnet = subnet,
                                     public_ip_address = ResourceId(id = public_ip_id)
                                 )]
                                ))
            self.network_interface = self.machine_name

        if self.vm_id: return

        if self.get_settled_resource():
            raise Exception("tried creating a virtual machine that already exists; "
                            "please run 'deploy --check' to fix this")

        root_disk_id = find_root_disk(defn.block_device_mapping)
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
                        name = self.machine_name+'-root',
                        virtual_hard_disk = VirtualHardDisk(uri = root_disk_spec['media_link']),
                        source_image = (None
                                        if root_disk_exists
                                        else VirtualHardDisk(uri = defn.root_disk_image_url) ),
                        operating_system_type = "Linux"
                    ),
                    data_disks = data_disks
                )
            )
        )
        print req.__dict__

        # we take a shortcut: wait for either provisioning to fail or for public ip to get assigned
        def check_req():
            return ((self.nrpc().public_ip_addresses.get(
                        self.resource_group, self.public_ip).public_ip_address.ip_address is not None)
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

        self.public_ipv4 = self.nrpc().public_ip_addresses.get(
                               self.resource_group, self.public_ip).public_ip_address.ip_address
        self.log("got IP: {0}".format(self.public_ipv4))
        self.update_ssh_known_hosts()

        for d_id, disk in defn.block_device_mapping.iteritems():
            self.update_block_device_mapping(d_id, disk)


    def after_activation(self, defn):
        # detach the volumes that are no longer in the deployment spec
        for d_id, disk in self.block_device_mapping.items():
            lun = device_name_to_lun(disk['device'])
            if d_id not in defn.block_device_mapping and lun is not None:
                disk_name = disk['name']

                # umount with -l flag in case if the regular umount run by activation failed
                if not disk.get('needs_attach', False):
                    if disk.get('encrypt', False):
                        dm = "/dev/mapper/{0}".format(disk_name)
                        self.log("unmounting device '{0}'...".format(dm))
                        self.run_command("umount -l {0}".format(dm), check=False)
                        self.run_command("cryptsetup luksClose {0}".format(dm), check=False)
                    else:
                        self.log("unmounting device '{0}'...".format(disk['device']))
                        self.run_command("umount -l {0}".format(disk['device']), check=False)

                try:
                    if not disk.get('needs_attach', False):
                        with self.deployment_lock:
                            self.log("detaching Azure disk '{0}'...".format(d_id))
                            req = self.sms().delete_data_disk(defn.hosted_service, defn.deployment,
                                                              defn.machine_name, lun, delete_vhd = False)
                            self.finish_request(req)
                        disk['needs_attach'] = True
                        self.update_block_device_mapping(d_id, disk)

                    if disk['is_ephemeral']:
                        self._delete_volume(disk_name, disk_id = d_id)
                    else:
                        self._wait_disk_detached(disk_name, disk_id = d_id)

                except azure.common.AzureMissingResourceHttpError:
                    self.warn("Azure disk '{0}' seems to have been destroyed already".format(d_id))

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
            with self.deployment_lock:
                self.state = self.STARTING
                self.log("starting Azure machine...")
                self.cmc().virtual_machines.start(self.resource_group, self.machine_name)
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
                self._delete_volume(disk['media_link'], disk_id = d_id)
            self.update_block_device_mapping(d_id, None)
            self._delete_encryption_key(d_id)

        if self.generated_encryption_keys != {}:
            if not self.depl.logger.confirm("{0} still has generated encryption keys for disks {1}; "
                                            "if the keys are deleted, the data will be lost even if you have "
                                            "a copy of the disks contents; are you sure you want to delete "
                                            "the remaining encryption keys?"
                                            .format(self.full_name, self.generated_encryption_keys.keys()) ):
                raise Exception("can't continue")

        if self.network_interface:
            self.log("destroying the network interface...")
            try:
                self.nrpc().network_interfaces.get(self.resource_group, self.network_interface)
                self.nrpc().network_interfaces.delete(self.resource_group, self.network_interface)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("seems to have been destroyed already")
            self.network_interface = None

        if self.public_ip:
            self.log("releasing the ip address...")
            try:
                self.nrpc().public_ip_addresses.get(self.resource_group, self.public_ip)
                self.nrpc().public_ip_addresses.delete(self.resource_group, self.public_ip)
            except azure.common.AzureMissingResourceHttpError:
                self.warn("seems to have been released already")
            self.public_ip = None
            self.obtain_ip = None
        return True


    def parse_blob_url(self, blob):
        match = re.match(r'https?://([^\./]+)\.[^/]+/([^/]+)/(.+)$', blob)
        return None if match is None else {
            "storage": match.group(1),
            "container": match.group(2),
            "name": match.group(3)
        }

    def backup(self, defn, backup_id):
        self.log("backing up {0} using ID '{1}'".format(self.full_name, backup_id))

        if sorted(defn.block_device_mapping.keys()) != sorted(self.block_device_mapping.keys()):
            self.warn("the list of disks currently deployed doesn't match the current deployment"
                     " specification; consider running 'deploy' first; the backup may be incomplete")

        backup = {}
        _backups = self.backups
        for d_id, disk in self.block_device_mapping.iteritems():
            media_link = self.sms().get_disk(disk["name"]).media_link
            self.log("snapshotting the BLOB {0} backing the Azure disk {1}".format(media_link, disk["name"]))
            blob = self.parse_blob_url(media_link)
            if blob["storage"] != self.storage:
                raise Exception("storage {1} provided in the deployment specification "
                                "doesn't match the storage of BLOB {1}"
                                .format(self.storage, blob_url))
            snapshot = self.bs().snapshot_blob(blob["container"], blob["name"],
                                               x_ms_meta_name_values = {
                                                   'nixops_backup_id': backup_id,
                                                   'description': "backup of disk {0} attached to {1}"
                                                                  .format(disk["name"], self.machine_name)
                                               })
            backup[media_link] = snapshot["x-ms-snapshot"]
            _backups[backup_id] = backup
            self.backups = _backups

    def restore(self, defn, backup_id, devices=[]):
        self.log("restoring {0} to backup '{1}'".format(self.full_name, backup_id))

        if self.vm_id:
            self.stop()
            self.log("temporarily deprovisioining {0}".format(self.full_name))
            self.destroy_resource()
            self._node_deleted()

        for d_id, disk in self.block_device_mapping.items():
            azure_disk = self.sms().get_disk(disk["name"])
            s_id = self.backups[backup_id].get(azure_disk.media_link, None)
            if s_id and (devices == [] or azure_disk.media_link in devices or
                         disk["name"] in devices or disk["device"] in devices):
                blob = self.parse_blob_url(azure_disk.media_link)
                if blob is None:
                    self.warn("failed to parse BLOB URL {0}; skipping"
                              .format(azure_disk.media_link))
                    continue
                if blob["storage"] != self.storage:
                    raise Exception("storage {1} provided in the deployment specification "
                                    "doesn't match the storage of BLOB {1}"
                                    .format(self.storage, blob_url))
                try:
                    self.bs().get_blob_properties(
                            blob["container"], "{0}?snapshot={1}"
                                                .format(blob["name"], s_id))
                except azure.common.AzureMissingResourceHttpError:
                    self.warn("snapsnot {0} for disk {1} is missing; skipping".format(s_id, d_id))
                    continue

                self._delete_volume(disk["name"], disk_id = d_id, delete_vhd = False)

                self.log("restoring BLOB {0} from snapshot"
                         .format(azure_disk.media_link, s_id))
                self.bs().copy_blob(blob["container"], blob["name"],
                                   "{0}?snapshot={1}"
                                   .format(azure_disk.media_link, s_id) )

                self.log("re-creating disk resource {0} for BLOB {1}"
                         .format(azure_disk.name, azure_disk.media_link))
                self._create_disk(azure_disk.os, azure_disk.label,
                                  azure_disk.media_link, azure_disk.name, azure_disk.os)
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
                    blob = self.parse_blob_url(blob_url)
                    if blob is None:
                        self.warn("failed to parse BLOB URL {0}; skipping".format(blob_url))
                    if blob["storage"] != self.storage:
                        raise Exception("storage {1} provided in the deployment specification "
                                        "doesn't match the storage of BLOB {1}"
                                        .format(self.storage, blob_url))

                    self.bs().delete_blob(blob["container"], blob["name"], snapshot_id)
                except azure.common.AzureMissingResourceHttpError:
                    self.warn('snapshot {0} of BLOB {1} not found; skipping'
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
                media_link = self.sms().get_disk(disk["name"]).media_link
                if not media_link in snapshots.keys():
                    backup_status = "incomplete"
                    info.append("{0} - {1} - not available in backup"
                                .format(self.name, d_id))
                else:
                    snapshot_id = snapshots[media_link]
                    processed.add(media_link)
                    blob = self.parse_blob_url(media_link)
                    if blob is None:
                        info.append("failed to parse BLOB URL {0}"
                                    .format(media_link))
                        backup_status = "unavailable"
                    elif blob["storage"] != self.storage:
                        info.append("storage {1} provided in the deployment specification "
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
        if self.subscription_id is None and self.certificate_path is None:
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
            d = self.sms().get_deployment_by_name(self.hosted_service, self.deployment)
            role_instance = next((r for r in d.role_instance_list if r.instance_name == self.machine_name), None)
            if role_instance is None:
                self.state = self.UNKNOWN
            else:
                res.is_up = role_instance.power_state == "Started"
                if not res.is_up: self.state = self.STOPPED
                if res.is_up:
                    # check that all disks are attached
                    res.disks_ok = True
                    for d_id, disk in self.block_device_mapping.iteritems():
                        if device_name_to_lun(disk["device"]) is None:
                            if vm.os_virtual_hard_disk.disk_name!=disk["name"]:
                                res.disks_ok = False
                                res.messages.append("different root disk instead of {0}".format(d_id))
                            else: continue
                        if all(disk["name"] != d.disk_name
                               for d in vm.data_virtual_hard_disks.data_virtual_hard_disks):
                            res.disks_ok = False
                            res.messages.append("disk {0} is detached".format(d_id))
                            try:
                                self.sms().get_disk(disk["name"])
                            except azure.common.AzureMissingResourceHttpError:
                                res.messages.append("disk {0} is destroyed".format(d_id))

                    self.handle_changed_property('public_ipv4', self.fetch_PIP())
                    self.update_ssh_known_hosts()

                    MachineState._check(self, res)

    def get_physical_spec(self):
        block_device_mapping = {}
        for d_id, disk in self.block_device_mapping.items():
            if (disk.get('encrypt', False)
                and disk.get('passphrase', "") == ""
                and self.generated_encryption_keys.get(d_id, None) is not None):
                block_device_mapping[disk["device"]] = {
                    'passphrase': Function("pkgs.lib.mkOverride 10",
                                           self.generated_encryption_keys[d_id], call=True),
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
                    'group': 'root',
                    'permissions': '0600',
                    'user': 'root'
                }
        return keys


    def create_after(self, resources, defn):
        from nixops.resources.azure_blob import AzureBLOBState
        from nixops.resources.azure_blob_container import AzureBLOBContainerState
        from nixops.resources.azure_storage import AzureStorageState
        from nixops.resources.azure_resource_group import AzureResourceGroupState
        from nixops.resources.azure_virtual_network import AzureVirtualNetworkState

        return {r for r in resources
                  if isinstance(r, AzureBLOBContainerState) or isinstance(r, AzureStorageState) or
                     isinstance(r, AzureBLOBState) or isinstance(r, AzureResourceGroupState) or
                     isinstance(r, AzureVirtualNetworkState)}

    # return ssh host and port formatted for ssh/known_hosts file
    def get_ssh_host_port(self):
        return self.public_ipv4

    @MachineState.ssh_port.getter
    def ssh_port(self):
        if self.public_ipv4:
            return super(AzureState, self).ssh_port
        return None

    def update_ssh_known_hosts(self):
        ssh_host_port = self.get_ssh_host_port()
        if ssh_host_port:
            known_hosts.add(ssh_host_port, self.public_host_key)

    def get_ssh_name(self):
        ip = self.public_ipv4
        if ip is None:
            raise Exception("{0} does not have a public IPv4 address and is not reachable "
                            .format(self.full_name))
        return ip

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.private_client_key)

    def get_ssh_flags(self, scp=False):
        return [ "-i", self.get_ssh_private_key_file() ] + super(AzureState, self).get_ssh_flags(scp = scp)
