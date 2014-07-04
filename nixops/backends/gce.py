# -*- coding: utf-8 -*-

import os
import sys
import socket
import struct

from nixops import known_hosts
from nixops.util import wait_for_tcp_port, ping_tcp_port
from nixops.util import attr_property, create_key_pair

from nixops.backends import MachineDefinition, MachineState

from nixops.gce_common import ResourceState, optional_string, optional_int
import nixops.resources.gce_static_ip
import nixops.resources.gce_disk
import nixops.resources.gce_network

import libcloud.common.google
from libcloud.compute.types import Provider, NodeState
from libcloud.compute.providers import get_driver


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

        self.machine_name = x.find("attr[@name='machineName']/string").get("value")

        self.region = x.find("attr[@name='region']/string").get("value")
        self.instance_type = x.find("attr[@name='instanceType']/string").get("value")
        self.project = x.find("attr[@name='project']/string").get("value")
        self.service_account = x.find("attr[@name='serviceAccount']/string").get("value")
        self.access_key_path = x.find("attr[@name='accessKey']/string").get("value")

        self.tags = sorted([e.get("value") for e in x.findall("attr[@name='tags']/list/string")])
        self.metadata = {k.get("name"): k.find("string").get("value") for k in x.findall("attr[@name='metadata']/attrs/attr")}


        self.automatic_restart = optional_string(x.find("attr[@name='scheduling']/attrs/attr[@name='automaticRestart']/bool"))
        self.on_host_maintenance = optional_string(x.find("attr[@name='scheduling']/attrs/attr[@name='onHostMaintenance']/string"))

        self.ipAddress = ( optional_string(x.find("attr[@name='ipAddress']/attrs/attr[@name='name']/string")) or
                           optional_string(x.find("attr[@name='ipAddress']/string")) )

        self.network = ( optional_string(x.find("attr[@name='network']/attrs/attr[@name='name']/string")) or
                         optional_string(x.find("attr[@name='network']/string")) )

        def opt_str(xml, name):
            return optional_string(xml.find("attrs/attr[@name='%s']/string" % name))
        def opt_int(xml, name):
            return optional_int(xml.find("attrs/attr[@name='%s']/int" % name))

        def opt_disk_name(dname):
          return ("{0}-{1}".format(self.machine_name, dname) if dname is not None else None)

        def f(xml):
            return {'disk': ( optional_string(xml.find("attrs/attr[@name='disk']/attrs/attr[@name='name']/string")) or
                              optional_string(xml.find("attrs/attr[@name='disk']/string")) ),
                    'disk_name': opt_disk_name(opt_str(xml, 'disk_name')),
                    'snapshot': opt_str(xml, 'snapshot'),
                    'image': opt_str(xml, 'image'),
                    'size': opt_int(xml, 'size'),
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


class GCEState(MachineState, ResourceState):
    """
    State of a Google Compute Engine machine.
    """
    @classmethod
    def get_type(cls):
        return "gce"

    machine_name = attr_property("gce.name", None)
    public_ipv4 = attr_property("publicIpv4", None)

    region = attr_property("gce.region", None)
    instance_type = attr_property("gce.instanceType", None)

    public_client_key = attr_property("gce.publicClientKey", None)
    private_client_key = attr_property("gce.privateClientKey", None)

    tags = attr_property("gce.tags", None, 'json')
    metadata = attr_property("gce.metadata", {}, 'json')
    automatic_restart = attr_property("gce.scheduling.automaticRestart", None, bool)
    on_host_maintenance = attr_property("gce.scheduling.onHostMaintenance", None)
    ipAddress = attr_property("gce.ipAddress", None)
    network = attr_property("gce.network", None)

    block_device_mapping = attr_property("gce.blockDeviceMapping", {}, 'json')

    backups = nixops.util.attr_property("gce.backups", {}, 'json')

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._conn = None

    @property
    def resource_id(self):
        return self.machine_name

    credentials_prefix = "deployment.gce"

    @property
    def full_name(self):
        return "GCE Machine '{0}'".format(self.machine_name)

    def node(self):
       return self.connect().ex_get_node(self.machine_name, self.region)

    def full_metadata(self, metadata):
        result = metadata.copy()
        result.update({'sshKeys': "root:{0}".format(self.public_client_key) })
        return result

    def gen_metadata(self, metadata):
        return {
          'kind': 'compute#metadata',
          'items': [ {'key': k, 'value': v} for k,v in metadata.iteritems() ]
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
        self.state = self.STOPPED
        for k,v in self.block_device_mapping.iteritems():
            v['needsAttach'] = True
            self.update_block_device_mapping(k, v)


    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, GCEDefinition)

        if self.vm_id or self.block_device_mapping:
            if self.project != self.defn_project(defn):
                raise Exception("Cannot change the project of a deployed {0}".format(self.full_name))

            if self.region != defn.region:
                raise Exception("Cannot change the region of a deployed {0}".format(self.full_name))

            if self.machine_name != defn.machine_name:
                raise Exception("Cannot change the instance name of a deployed {0}".format(self.full_name))

        self.set_common_state(defn)
        self.copy_credentials(defn)
        self.machine_name = defn.machine_name

        if not self.public_client_key:
            (private, public) = create_key_pair()
            self.public_client_key = public
            self.private_client_key = private

        recreate = False

        if check:
            try:
                node = self.node()
                if self.vm_id:

                    if node.state == NodeState.TERMINATED:
                        if allow_reboot:
                            recreate = True
                            self.warn("The instance is terminated. Will restart...")
                        else:
                            self.warn("The instance is terminated. Run with --allow-reboot to restart it.")
                        self.state = self.STOPPED

                    self.public_ipv4 = self.warn_if_changed(self.public_ipv4,
                                                            node.public_ips[0] if node.public_ips else None,
                                                            'IP address')
                    if self.ipAddress:
                        try:
                            address = self.connect().ex_get_address(self.ipAddress)
                            if self.public_ipv4 and self.public_ipv4 != address.address:
                                self.warn("Static IP Address {0} assigned to this machine has unexpectely "
                                          "changed from {1} to {2} most likely due to being redeployed"
                                          .format(self.ipAddress, self.public_ipv4, address.address) )
                                self.ipAddress = None

                        except libcloud.common.google.ResourceNotFoundError:
                            self.warn("Static IP Address resource {0} used by this machine has been destroyed. "
                                      "It is likely that the machine is still holding the address itself ({1}) "
                                      "and this is your last chance to reclaim it before it gets "
                                      "lost in a reboot.".format(self.ipAddress, self.public_ipv4) )

                    self.tags = self.warn_if_changed(self.tags, sorted(node.extra['tags']), 'tags')

                    # check that all disks are attached
                    for k, v in self.block_device_mapping.iteritems():
                        disk_name = v['disk_name'] or v['disk']
                        if( all(d.get("deviceName", None) != disk_name for d in node.extra['disks']) and
                              not v.get('needsAttach', False) ):
                            self.warn("Disk {0} seems to have been detached behind our back. Will reattach...".format(disk_name))
                            v['needsAttach'] = True
                            self.update_block_device_mapping(k, v)

                    # FIXME: check that no extra disks are attached?
                else:
                    self.warn("{0} exists, but isn't supposed to. Probably, this is the result "
                              "of a botched creation attempt and can be fixed by deletion. However, this also "
                              "could be a resource name collision, and valuable data could be lost. "
                              "Before proceeding, please ensure that the instance doesn't contain useful data."
                              .format(self.full_name))
                    self.confirm_destroy(node, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                if self.vm_id:
                    self.warn("The instance seems to have been destroyed behind our back.")
                    if not allow_recreate: raise Exception("Use --allow-recreate, to fix.")
                    self._node_deleted()

        if self.vm_id:
            if self.instance_type != defn.instance_type:
                recreate = True
                self.warn("Change of the instance type requires a reboot")

            if self.network != defn.network:
                recreate = True
                self.warn("Change of the network requires a reboot")

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
                        self.confirm_destroy(disk, disk_name)

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
                    extra_msg = " from snapshot '{0}'".format(v['snapshot'])
                elif v['image']:
                    extra_msg = " from image '{0}'".format(v['image'])
                else:
                    extra_msg = ""
                self.log_start("Creating GCE disk of {0} GiB{1}..."
                              .format(v['size'] if v['size'] else "auto", extra_msg))
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

        if self.vm_id:
            for k, v in self.block_device_mapping.iteritems():
                defn_v = defn.block_device_mapping.get(k, None)
                if defn_v and not v.get('needsAttach', False):
                    if v['bootDisk'] != defn_v['bootDisk']:
                        recreate = True
                        self.warn("Change of the boot disk requires a reboot")
                    if v['readOnly'] != defn_v['readOnly']:
                        recreate = True
                        self.warn("Remounting disk as ro/rw requires a reboot")

        if recreate:
            if not allow_reboot:
                raise Exception("Reboot is required for the requested changes. Please run with --allow-reboot.")
            self.log("Need to recreate the instance for the changes to take effect. Deleting...")
            self.node().destroy()
            self._node_deleted()

        if not self.vm_id:
            self.log_start("Creating '{0}'...".format(self.full_name))
            boot_disk = next(v for k,v in self.block_device_mapping.iteritems() if v.get('bootDisk', False))
            try:
                node = self.connect().create_node(self.machine_name, defn.instance_type, 'none',
                                 location = self.connect().ex_get_zone(defn.region),
                                 ex_boot_disk = self.connect().ex_get_volume(boot_disk['disk_name'] or boot_disk['disk'], boot_disk['region']),
                                 ex_metadata = self.full_metadata(defn.metadata), ex_tags = defn.tags,
                                 external_ip = (self.connect().ex_get_address(defn.ipAddress) if defn.ipAddress else 'ephemeral'),
                                 ex_network = (defn.network if defn.network else 'default') )
            except libcloud.common.google.ResourceExistsError:
                raise Exception("Tried creating an instance that already exists. Please run ‘deploy --check’ to fix this.")
            self.log_end("done.")
            self.vm_id = self.machine_name
            self.state = self.STARTING
            self.ssh_pinged = False
            self.tags = defn.tags
            self.region = defn.region
            self.instance_type = defn.instance_type
            self.metadata = defn.metadata
            self.ipAddress = defn.ipAddress
            self.network = defn.network
            self.public_ipv4 = node.public_ips[0]
            self.log("got IP: {0}".format(self.public_ipv4))
            known_hosts.remove(self.public_ipv4)
            for k,v in self.block_device_mapping.iteritems():
                v['needsAttach'] = True
                self.update_block_device_mapping(k, v)

        # Attach missing volumes
        for k, v in self.block_device_mapping.items():
            defn_v = defn.block_device_mapping.get(k, None)
            if v.get('needsAttach', False) and defn_v:
                disk_name = v['disk_name'] or v['disk']
                disk_region = v.get('region', None)
                v['readOnly'] = defn_v['readOnly']
                v['bootDisk'] = defn_v['bootDisk']
                self.log("attaching GCE disk ‘{0}’...".format(disk_name))
                if not v.get('bootDisk', False):
                    self.connect().attach_volume(self.node(), self.connect().ex_get_volume(disk_name, disk_region), 
                                   device = disk_name,
                                   ex_mode = ('READ_ONLY' if v['readOnly'] else 'READ_WRITE'))
                del v['needsAttach']
                self.update_block_device_mapping(k, v)

        if( self.metadata != defn.metadata or
           (check and sorted(self.gen_metadata(self.full_metadata(defn.metadata))['items']) != sorted(node.extra['metadata'].get('items',[]))) ):
            self.log('setting new metadata values')
            node = self.node()
            meta = self.gen_metadata(self.full_metadata(defn.metadata))
            request = '/zones/%s/instances/%s/setMetadata' % (node.extra['zone'].name,
                                                        node.name)
            metadata_data = {}
            metadata_data['items'] = meta['items']
            metadata_data['kind'] = meta['kind']
            metadata_data['fingerprint'] = node.extra['metadata']['fingerprint']

            self.connect().connection.async_request(request, method='POST',
                                          data=metadata_data)
            self.metadata = defn.metadata

        if self.tags != defn.tags:
            self.log('Updating tags')
            self.connect().ex_set_node_tags(self.node(), defn.tags)
            self.tags = defn.tags

        if self.public_ipv4 and self.ipAddress != defn.ipAddress:
            self.log("Detaching old IP address {0}".format(self.public_ipv4))
            self.connect().connection.async_request(
                "/zones/{0}/instances/{1}/deleteAccessConfig?accessConfig=External+NAT&networkInterface=nic0"
                .format(self.region, self.machine_name), method = 'POST')
            self.public_ipv4 = None
            self.ipAddress = None

        if self.public_ipv4 is None:
            self.log("Attaching IP address {0}".format(defn.ipAddress or "[Ephemeral]"))
            self.connect().connection.async_request(
                "/zones/{0}/instances/{1}/addAccessConfig?networkInterface=nic0"
                .format(self.region, self.machine_name), method = 'POST', data = {
                  'kind': 'compute#accessConfig',
                  'type': 'ONE_TO_ONE_NAT',
                  'name': 'External NAT',
                  'natIP': self.connect().ex_get_address(defn.ipAddress).address if defn.ipAddress else None
                })
            self.ipAddress = defn.ipAddress
            self.public_ipv4 = self.node().public_ips[0]
            self.log("got IP: {0}".format(self.public_ipv4))
            known_hosts.remove(self.public_ipv4)
            self.ssh.reset()
            self.ssh_pinged = False

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
        if not self.vm_id:
            self.warn("You can start this machine by (re)creating it with deploy.")
            return

        node = self.node()

        if node.state == NodeState.TERMINATED:
            self.warn("GCE machines can't be started directly after being terminated."
                      " You can re-start the machine by re-creating it with deploy --check --allow-reboot.")

        if node.state == NodeState.STOPPED:
            self.warn("Kicking the machine with a hard reboot to start it.")
            self.reboot(hard=True)


    def stop(self):
        if not self.vm_id: return

        self.warn("GCE machines can't be started easily after being stopped. Consider rebooting instead.")

        try:
            node = self.node()
        except libcloud.common.google.ResourceNotFoundError:
            self.warn("seems to have been destroyed already")
            self._node_deleted()
            return

        if node.state != NodeState.TERMINATED:
            self.log_start("stopping GCE machine... ")
            self.run_command("poweroff", check=False)
            self.state = self.STOPPING

            def check_stopped():
                self.log_continue(".")
                return self.node().state == NodeState.TERMINATED
            if nixops.util.check_wait(check_stopped, initial=3, max_tries=100, exception=False): # = 5 min
                self.log_end("done")
            else:
                self.log_end("(timed out)")

        self.state = self.STOPPED
        self.ssh.reset()

    def destroy(self, wipe=False):
        if wipe:
            log.warn("Wipe is not supported.")
        try:
            node = self.node()
            question = "are you sure you want to destroy {0}?"
            if not self.depl.logger.confirm(question.format(self.full_name)):
                return False

            self.log_start("destroying the GCE machine...")
            node.destroy()

        except libcloud.common.google.ResourceNotFoundError:
            self.warn("seems to have been destroyed already")
        self._node_deleted()

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

                self.log("Unmounting device ‘{0}’...".format(disk_name))
                if v.get('encrypt', False):
                    dm = "/dev/mapper/{0}".format(disk_name)
                    self.run_command("umount -l {0}".format(dm), check=False)
                    self.run_command("cryptsetup luksClose {0}".format(dm), check=False)
                else:
                    self.run_command("umount -l {0}".format(k), check=False)

                node = self.node()
                try:
                    if not v.get('needsAttach', False):
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
                res.messages.append("Instance has been terminated, can't be directly (re)started\n"
                                    "and can only be destroyed due the to limitations imposed by GCE.\n"
                                    "Run deploy --check --allow-reboot to re-create it.")
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

    def create_after(self, resources):
        # Just a check for all GCE resource classes
        return {r for r in resources if
                isinstance(r, nixops.resources.gce_static_ip.GCEStaticIPState) or
                isinstance(r, nixops.resources.gce_disk.GCEDiskState) or
                isinstance(r, nixops.resources.gce_network.GCENetworkState)}


    def backup(self, defn, backup_id):
        self.log("Backing up {0} using id ‘{1}’".format(self.full_name, backup_id))

        if sorted(defn.block_device_mapping.keys()) != sorted(self.block_device_mapping.keys()):
            self.warn("The list of disks currently deployed doesn't match the current deployment"
                     " specification. Consider running deploy. The backup may be incomplete.")

        backup = {}
        _backups = self.backups
        for k, v in self.block_device_mapping.iteritems():
            disk_name = v['disk_name'] or v['disk']
            volume = self.connect().ex_get_volume(disk_name, v.get('region', None))
            snapshot_name = "backup-{0}-{1}".format(backup_id, disk_name[-32:])
            self.log_start("creating snapshot of disk ‘{0}’: ‘{1}’".format(disk_name, snapshot_name))
            snapshot = self.connect().create_volume_snapshot(volume, snapshot_name)
            self.log_end('done.')

            backup[disk_name] = snapshot.name
            _backups[backup_id] = backup
            self.backups = _backups

    def restore(self, defn, backup_id, devices=[]):
        self.log("Restoring {0} to backup ‘{1}’".format(self.full_name, backup_id))

        self.stop()

        # need to destroy the machine to get at the root disk
        if self.vm_id:
            try:
                self.log("Tearing down the machine. You will need to run deploy --allow-reboot to start it.")
                self.node().destroy()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("The machine seems to have been destroyed already")
            self._node_deleted()

        for k, v in self.block_device_mapping.items():
            disk_name = v['disk_name'] or v['disk']
            s_id = self.backups[backup_id].get(disk_name, None)
            if s_id and (devices == [] or k in devices or disk_name in devices):
                try:
                    snapshot = self.connect().ex_get_snapshot(s_id)
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn("Snapsnot {0} for disk {1} is missing. Skipping".format(s_id, disk_name))
                    continue

                try:
                    self.log("destroying disk {0}".format(disk_name))
                    self.connect().ex_get_volume(disk_name, v.get('region', None)).destroy()
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn("disk {0} seems to have been destroyed already".format(disk_name))

                self.log("creating disk {0} from snapshot ‘{1}’".format(disk_name, s_id))
                self.connect().create_volume(None, disk_name, v.get('region', None),
                                             snapshot = snapshot, use_existing= False)

    def remove_backup(self, backup_id):
        self.log('removing backup {0}'.format(backup_id))
        _backups = self.backups
        if not backup_id in _backups.keys():
            self.warn('backup {0} not found, skipping'.format(backup_id))
        else:
            for d_name, snapshot_id in _backups[backup_id].iteritems():
                try:
                    self.log('removing snapshot {0}'.format(snapshot_id))
                    self.connect().ex_get_snapshot(snapshot_id).destroy()
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn('snapshot {0} not found, skipping'.format(snapshot_id))

            _backups.pop(backup_id)
            self.backups = _backups

    def get_backups(self):
        self.connect()
        backups = {}
        for b_id, snapshots in self.backups.iteritems():
            backups[b_id] = {}
            backup_status = "complete"
            info = []
            for k, v in self.block_device_mapping.items():
                disk_name = v['disk_name'] or v['disk']
                if not disk_name in snapshots.keys():
                    backup_status = "incomplete"
                    info.append("{0} - {1} - Not available in backup".format(self.name, disk_name))
                else:
                    snapshot_id = snapshots[disk_name]
                    try:
                        snapshot = self.connect().ex_get_snapshot(snapshot_id)
                    except libcloud.common.google.ResourceNotFoundError:
                        info.append("{0} - {1} - {2} - Snapshot has disappeared".format(self.name, disk_name, snapshot_id))
                        backup_status = "unavailable"
            for d_name, s_id in snapshots.iteritems():
                if not any(d_name == v['disk_name'] or d_name == v['disk'] for k,v in self.block_device_mapping.iteritems()):
                    info.append("{0} - {1} - {2} - A snapshot of a disk that is not or no longer deployed".format(self.name, d_name, s_id))
            backups[b_id]['status'] = backup_status
            backups[b_id]['info'] = info
        return backups


    def get_ssh_name(self):
        if not self.public_ipv4:
            raise Exception("{0} does not have a public IPv4 address (yet)".format(self.full_name))
        return self.public_ipv4

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.private_client_key)

    def get_ssh_flags(self):
        return [ "-i", self.get_ssh_private_key_file() ]