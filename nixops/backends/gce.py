# -*- coding: utf-8 -*-

import os
import sys
import socket
import struct

from nixops import known_hosts
from nixops.util import wait_for_tcp_port, ping_tcp_port
from nixops.util import attr_property, create_key_pair

from nixops.backends import MachineDefinition, MachineState

import libcloud.common.google
from libcloud.compute.types import Provider, NodeState
from libcloud.compute.providers import get_driver

import uuid


class GCEDefinition(MachineDefinition):
    """
    Definition of a Google Compute Engine machine.
    """
    @classmethod
    def get_type(cls):
        return "gce"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='gce']/attrs")
        assert x is not None

        self.region = x.find("attr[@name='region']/string").get("value")
        self.instance_type = x.find("attr[@name='instanceType']/string").get("value")
        self.project = x.find("attr[@name='project']/string").get("value")
        self.service_account = x.find("attr[@name='serviceAccount']/string").get("value")
        self.access_key_path = x.find("attr[@name='accessKey']/string").get("value")

        self.tags = [e.get("value") for e in x.findall("attr[@name='tags']/list/string")]
        self.metadata = {k.get("name"): k.find("string").get("value") for k in x.findall("attr[@name='metadata']/attrs/attr")}

        def optional_str(elem):
            return (elem.get("value") if elem is not None else None)

        self.automatic_restart = optional_str(x.find("attr[@name='scheduling']/attrs/attr[@name='automaticRestart']/bool"))
        self.on_host_maintenance = optional_str(x.find("attr[@name='scheduling']/attrs/attr[@name='onHostMaintenance']/string"))

        self.ipAddress = ( optional_str(x.find("attr[@name='ipAddress']/attrs/attr[@name='name']/string")) or
                           optional_str(x.find("attr[@name='ipAddress']/string")) )

        self.network = ( optional_str(x.find("attr[@name='network']/attrs/attr[@name='name']/string")) or
                         optional_str(x.find("attr[@name='network']/string")) )

        def opt_str(xml, name):
          elem = xml.find("attrs/attr[@name='%s']/string" % name)
          return(elem.get("value") if elem is not None else None)
        def opt_int(xml, name):
          elem = xml.find("attrs/attr[@name='%s']/int" % name)
          return(int(elem.get("value")) if elem is not None else None)

        def f(xml):
            return {'disk': ( optional_str(xml.find("attrs/attr[@name='disk']/attrs/attr[@name='name']/string")) or
                              optional_str(xml.find("attrs/attr[@name='disk']/string")) ),
                    'disk_name': opt_str(xml, 'disk_name'),
                    'snapshot': opt_str(xml, 'snapshot'),
                    'image': opt_str(xml, 'image'),
                    'size': opt_int(xml, 'size'),
                    #'fsType': xml.find("attrs/attr[@name='fsType']/string").get("value"),
                    'deleteOnTermination': xml.find("attrs/attr[@name='deleteOnTermination']/bool").get("value") == "true",
                    'readOnly': xml.find("attrs/attr[@name='readOnly']/bool").get("value") == "true",
                    'bootDisk': xml.find("attrs/attr[@name='bootDisk']/bool").get("value") == "true",
                    'encrypt': xml.find("attrs/attr[@name='encrypt']/bool").get("value") == "true",
                    'passphrase': xml.find("attrs/attr[@name='passphrase']/string").get("value")}

        self.block_device_mapping = {k.get("name"): f(k) for k in x.findall("attr[@name='blockDeviceMapping']/attrs/attr")}

        boot_devices = [k for k,v in self.block_device_mapping.iteritems() if v['bootDisk']]
        if len(boot_devices) == 0:
            raise Exception("Machine {0} must have a boot device.".format(self.name))
        if len(boot_devices) > 1:
            raise Exception("Machine {0} must have exactly one boot device.".format(self.name))

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region or self.zone or "???")


class GCEState(MachineState):
    """
    State of a Google Compute Engine machine.
    """
    @classmethod
    def get_type(cls):
        return "gce"

    state = attr_property("state", MachineState.MISSING, int)
    public_ipv4 = attr_property("publicIpv4", None)

    region = attr_property("gce.region", None)
    instance_type = attr_property("gce.instanceType", None)
    project = attr_property("gce.project", None)
    service_account = attr_property("gce.serviceAccount", None)
    access_key_path = attr_property("gce.accessKey", None)

    public_host_key = attr_property("gce.publicHostKey", None)
    private_host_key = attr_property("gce.privateHostKey", None)

    tags = attr_property("gce.tags", None, 'json')
    metadata = attr_property("gce.metadata", {}, 'json')
    automatic_restart = attr_property("gce.scheduling.automaticRestart", None, bool)
    on_host_maintenance = attr_property("gce.scheduling.onHostMaintenance", None)
    ipAddress = attr_property("gce.ipAddress", None)
    network = attr_property("gce.network", None)

    block_device_mapping = attr_property("gce.blockDeviceMapping", {}, 'json')

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._conn = None

    @property
    def resource_id(self):
        return self.vm_id

    def connect(self):
        if self._conn: return self._conn

        service_account = self.service_account or os.environ.get('GCE_SERVICE_ACCOUNT')
        if not service_account:
            raise Exception("please set ‘deployment.gce.serviceAccount’ or $GCE_SERVICE_ACCOUNT")

        access_key_path = self.access_key_path or os.environ.get('ACCESS_KEY_PATH')
        if not access_key_path:
            raise Exception("please set ‘deployment.gce.accessKey’ or $ACCESS_KEY_PATH")

        project = self.project or os.environ.get('GCE_PROJECT')
        if not project:
            raise Exception("please set ‘deployment.gce.project’ or $GCE_PROJECT")

        self._conn = get_driver(Provider.GCE)(service_account, access_key_path, project = project)
        return self._conn

    def node(self):
       return self.connect().ex_get_node(self.name, self.region)

    def gen_metadata(self, metadata):
        return {
          'kind': 'compute#metadata',
          'items': [ {'key': 'sshKeys', 'value': "root:{0}".format(self.public_host_key) } ] +
                   [ {'key': k, 'value': v} for k,v in metadata.iteritems() ]
        }

    def update_block_device_mapping(self, k, v):
        x = self.block_device_mapping
        if v == None:
            x.pop(k, None)
        else:
            x[k] = v
        self.block_device_mapping = x

    def _delete_volume(self, volume_id, region, allow_keep=False):
        if not self.depl.logger.confirm("are you sure you want to destroy GCE disk ‘{0}’?".format(volume_id)):
            if allow_keep:
                return
            else:
                raise Exception("not destroying GCE disk ‘{0}’".format(volume_id))
        self.log("destroying GCE disk ‘{0}’...".format(volume_id))
        try:
            disk = self.connect().ex_get_volume(volume_id, region)
            disk.destroy()
        except libcloud.common.google.ResourceNotFoundError:
            self.warn("seems to have been destroyed already")


    def _node_deleted(self):
        self.vm_id = None
        for k,v in self.block_device_mapping.iteritems():
            v['needsAttach'] = True
            self.update_block_device_mapping(k, v)


    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, GCEDefinition)

        if self.vm_id:
            if self.project != defn.project:
                raise Exception("Cannot change the project of a deployed GCE machine {0}".format(defn.name))

            if self.region != defn.region:
                raise Exception("Cannot change the region of a deployed GCE machine {0}".format(defn.name))

        self.set_common_state(defn)
        self.project = defn.project
        self.service_account = defn.service_account
        self.access_key_path = defn.access_key_path

        if not self.public_host_key:
            (private, public) = create_key_pair(type='dsa')
            with self.depl._db:
                self.public_host_key = public
                self.private_host_key = private

        if check:
            try:
                node = self.node()
                if self.vm_id:
                    if self.public_ipv4 != node.public_ips[0]:
                        self.warn("IP address has unexpectedly changed from {0} to {1}".format(self.public_ipv4, node.public_ips[0]))
                        self.public_ipv4 = node.public_ips[0]

                    # check that all disks are attached
                    for k, v in self.block_device_mapping.iteritems():
                        disk_name = v['disk_name'] or v['disk']
                        if all(d.get("deviceName", None) != disk_name for d in node.extra['disks']):
                            self.warn("Disk {0} seems to have been detached behind our back. Will reattach...".format(disk_name))
                            v['needsAttach'] = True
                            self.update_block_device_mapping(k, v)

                    # FIXME: check that no extra disks are attached?
                else:
                    self.warn("The instance ‘{0}’ exists, but isn't supposed to. Probably, this is the result "
                              "of a botched creation attempt and can be fixed by deletion. However, this also "
                              "could be a resource name collision, and valuable data could be lost. "
                              "Before proceeding, please ensure that the instance doesn't contain useful data."
                              .format(self.name))
                    if self.depl.logger.confirm("Are you sure you want to destroy the existing instance ‘{0}’?".format(self.name)):
                        self.log_start("destroying...")
                        node.destroy()
                        self.log_end("done.")
                    else: raise Exception("Can't proceed further.")


            except libcloud.common.google.ResourceNotFoundError:
                if self.vm_id:
                    self.warn("The instance seems to have been destroyed behind our back.")
                    if not allow_recreate: raise Exception("Use --allow-recreate, to fix.")
                    self._node_deleted()

        recreate = False

        if self.vm_id and self.instance_type != defn.instance_type:
            if allow_reboot:
                recreate = True
            else:
                raise Exception("cannot change the instance type of a running instance, unless reboots are allowed")

        if self.vm_id and self.ipAddress != defn.ipAddress:
            if allow_reboot:
                recreate = True
            else:
                raise Exception("cannot change the ip address of a running instance, unless reboots are allowed")

        if self.vm_id and self.network != defn.network:
            if allow_reboot:
                recreate = True
            else:
                raise Exception("cannot change the network of a running instance, unless reboots are allowed")

        #TODO: check if ro or bootdisk bool has changed

        if check:
            for k,v in defn.block_device_mapping.iteritems():
                disk_name = v['disk_name'] or v['disk']
                try:
                    disk = self.connect().ex_get_volume(disk_name, v.get('region', None) )
                    if k not in self.block_device_mapping and v['disk_name']:
                        self.warn("GCE disk ‘{0}’ exists, but isn't supposed to. Probably, this is the result "
                              "of a botched creation attempt and can be fixed by deletion. However, this also "
                              "could be a resource name collision, and valuable data could be lost. "
                              "Before proceeding, please ensure that the disk doesn't contain useful data."
                              .format(disk_name))
                        if self.depl.logger.confirm("Are you sure you want to destroy the existing disk ‘{0}’?".format(disk_name)):
                            self.log_start("destroying...")
                            disk.destroy()
                            self.log_end("done.")
                        else: raise Exception("Can't proceed further.")
                except libcloud.common.google.ResourceNotFoundError:
                    if v['disk']:
                        raise Exception("External disk ‘{0}’ is required but doesn't exist.".format(disk_name))
                    if k in self.block_device_mapping and v['disk_name']:
                        self.warn("Disk ‘{0}’ is supposed to exist, but is missing. Will recreate...".format(disk_name))
                        self.update_block_device_mapping(k, None)

        # create missing disks
        for k, v in defn.block_device_mapping.iteritems():
            if k in self.block_device_mapping: continue
            if v['disk'] is None:
                if v['snapshot']:
                    self.log_start("creating GCE disk of {0} GiB from snapshot ‘{1}’...".format(v['size'] if v['size'] else "auto", v['snapshot']))
                elif v['image']:
                    self.log_start("creating GCE disk of {0} GiB from image ‘{1}’...".format(v['size'] if v['size'] else "auto", v['image']))
                else:
                    self.log_start("creating GCE disk of {0} GiB...".format(v['size']))

                v['region'] = defn.region
                try:
                    self.connect().create_volume(v['size'], v['disk_name'], v['region'],
                                                  snapshot = v['snapshot'], image = v['image'],
                                                  use_existing= False)
                except libcloud.common.google.ResourceExistsError:
                    raise Exception("Tried creating a disk that already exists. Please run ‘deploy --check’ to fix this.")
                self.log_end('done.')
            v['needsAttach'] = True
            self.update_block_device_mapping(k, v)

        if recreate:
            self.log("Need to recreate the instance for the changes to take effect. Deleting...")
            self.node().destroy()
            self._node_deleted()

        if not self.vm_id:
            self.log_start("creating machine...")
            boot_disk = next(v for k,v in self.block_device_mapping.iteritems() if v.get('bootDisk', False))
            try:
                self.connect().create_node(self.name, defn.instance_type, 'nixos-14-04pre-d215564-x86-64-linux',
                                 location = self.connect().ex_get_zone(defn.region),
                                 ex_boot_disk = self.connect().ex_get_volume(boot_disk['disk_name'] or boot_disk['disk'], boot_disk['region']),
                                 ex_metadata = self.gen_metadata(defn.metadata), ex_tags = defn.tags,
                                 external_ip = (self.connect().ex_get_address(defn.ipAddress) if defn.ipAddress else 'ephemeral'),
                                 ex_network = (defn.network if defn.network else 'default') )
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating an instance that already exists. Please run ‘deploy --check’ to fix this.")
            self.log_end("done.")
            self.public_ipv4 = self.node().public_ips[0]
            self.log("got IP: {0}".format(self.public_ipv4))
            self.tags = defn.tags
            self.region = defn.region
            self.instance_type = defn.instance_type
            self.metadata = defn.metadata
            self.ipAddress = defn.ipAddress
            self.network = defn.network
            known_hosts.remove(self.public_ipv4)
            self.vm_id = "nixops-{0}-{1}".format(self.depl.uuid, self.name)

        # Attach missing volumes
        for k, v in self.block_device_mapping.items():
            if v.get('needsAttach', False) and not v.get('bootDisk', False):
                disk_name = v['disk_name'] or v['disk']
                disk_region = v.get('region', None)
                self.log("attaching GCE disk ‘{0}’...".format(disk_name))
                self.connect().attach_volume(self.node(), self.connect().ex_get_volume(disk_name, disk_region), 
                                   device = disk_name,
                                   ex_mode = ('READ_ONLY' if v['readOnly'] else 'READ_WRITE'))
                del v['needsAttach']
                self.update_block_device_mapping(k, v)

        if check or self.metadata != defn.metadata:
            self.log('setting new metadata values')
            node = self.node()
            meta = self.gen_metadata(defn.metadata)
            request = '/zones/%s/instances/%s/setMetadata' % (node.extra['zone'].name,
                                                        node.name)
            metadata_data = {}
            metadata_data['items'] = meta['items']
            metadata_data['kind'] = meta['kind']
            metadata_data['fingerprint'] = node.extra['metadata']['fingerprint']

            self.connect().connection.async_request(request, method='POST',
                                          data=metadata_data)
            self.metadata = defn.metadata

        if check  or sorted(self.tags) != sorted(defn.tags):
            self.log('setting new tag values')
            self.connect().ex_set_node_tags(self.node(), defn.tags)
            self.tags = defn.tags

        if recreate or check or self.automatic_restart != defn.automatic_restart or self.on_host_maintenance != defn.on_host_maintenance:
            self.connect().ex_set_node_scheduling(self.node(),
                                                  automatic_restart = defn.automatic_restart,
                                                  on_host_maintenance = defn.on_host_maintenance)
            self.automatic_restart = defn.automatic_restart
            self.on_host_maintenance = defn.on_host_maintenance

    def reboot(self, hard=False):
        if hard:
            self.log_start("sending hard reset to GCE machine...")
            self.node().reboot()
            self.log_end("done.")
            self.state = self.STARTING
        else:
            MachineState.reboot(self, hard=hard)

    def start(self):
        self.warn("GCE machines can't be started.")

    def stop(self):
        self.warn("GCE machines can't be started after being stopped. Consider rebooting instead.")

    def destroy(self, wipe=False):
        try:
            node = self.node()
            if wipe:
                question = "are you sure you want to completely erase {0}?"
            else:
                question = "are you sure you want to destroy {0}?"
            question_target = "GCE machine ‘{0}’?".format(self.name)
            if not self.depl.logger.confirm(question.format(question_target)):
                return False

            self.log_start("destroying the GCE machine...")
            node.destroy()
 
        except libcloud.common.google.ResourceNotFoundError:
            self.warn("seems to have been destroyed already")

        # Destroy volumes created for this instance.
        for k, v in self.block_device_mapping.items():
            if v.get('deleteOnTermination', False):
                self._delete_volume(v['disk_name'], v['region'])
            self.update_block_device_mapping(k, None)
        self.log_end("done.")

        return True


    def after_activation(self, defn):
        # Detach volumes that are no longer in the deployment spec.
        for k, v in self.block_device_mapping.items():
            if k not in defn.block_device_mapping:
                disk_name = v['disk'] or v['disk_name']

                self.log("detaching device ‘{0}’...".format(k))
                if v.get('encrypt', False):
                    dm = k.replace("/dev/disk/by-id/", "/dev/mapper/")
                    self.run_command("umount -l {0}".format(dm), check=False)
                    self.run_command("cryptsetup luksClose {0}".format(k.replace("/dev/disk/by-id/", "")), check=False)
                else:
                    self.run_command("umount -l {0}".format(k), check=False)

                node = self.node()
                try:
                    self.log("detaching GCE disk ‘{0}’...".format(disk_name))
                    volume = self.connect().ex_get_volume(disk_name, v.get('region', None) )
                    self.connect().detach_volume(volume, node)
                    v['needsAttach'] = True
                    self.update_block_device_mapping(k, v)
                    if v.get('deleteOnTermination', False):
                        self._delete_volume(disk_name, v['region'])
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn("GCE disk ‘{0}’ seems to have been destroyed already".format(disk_name))

                self.update_block_device_mapping(k, None)


    def get_console_output(self):
        node = self.node()
        if node.state == NodeState.TERMINATED:
          raise Exception("cannot get console output of a state=TERMINATED machine ‘{0}’".format(self.name))
        request = '/zones/%s/instances/%s/serialPort' % (node.extra['zone'].name, node.name)
        return self.connect().connection.request(request, method='GET').object['contents']


    def _check(self, res):
        try:
            node = self.node()
            res.exists = True
            res.is_up = node.state == NodeState.RUNNING or node.state == NodeState.REBOOTING
            if node.state == NodeState.REBOOTING or node.state == NodeState.PENDING: self.state = self.STARTING
            if node.state == NodeState.STOPPED: self.state = self.STOPPED
            if node.state == NodeState.UNKNOWN: self.state = self.UNKNOWN
            if node.state == NodeState.TERMINATED:
                self.state = self.UNKNOWN # FIXME: there's no corresponding status
                res.messages.append("Instance has been terminated, can't be (re)started\n"
                                    "and can only be destroyed due the to limitations of GCE.")
            if node.state == NodeState.RUNNING:
                # check that all disks are attached
                res.disks_ok = True
                for k, v in self.block_device_mapping.iteritems():
                    disk_name = v['disk_name'] or v['disk']
                    if all(d.get("deviceName", None) != disk_name for d in node.extra['disks']):
                        res.disks_ok = False
                        res.messages.append("Disk {0} is detached".format(disk_name))
                        try:
                            disk = self.connect().ex_get_volume(disk_name, v.get('region', None))
                        except libcloud.common.google.ResourceNotFoundError:
                            res.messages.append("Disk {0} is destroyed".format(disk_name))

                MachineState._check(self, res)
        except libcloud.common.google.ResourceNotFoundError:
            res.exists = False
            res.is_up = False
            self.state = self.MISSING;


    def get_ssh_name(self):
        if not self.public_ipv4:
            raise Exception("GCE machine ‘{0}’ does not have a public IPv4 address (yet)".format(self.name))
        return self.public_ipv4

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.private_host_key)

    def get_ssh_flags(self):
        return [ "-i", self.get_ssh_private_key_file() ]