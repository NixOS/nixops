# -*- coding: utf-8 -*-

import time

from nixops import known_hosts
from nixops.util import attr_property, create_key_pair, generate_random_string
from nixops.nix_expr import Function, RawValue, Call

from nixops.backends import MachineDefinition, MachineState

from nixops.gce_common import ResourceDefinition, ResourceState
import nixops.resources.gce_static_ip
import nixops.resources.gce_disk
import nixops.resources.gce_image
import nixops.resources.gce_network

import libcloud.common.google
from libcloud.compute.types import NodeState


class GCEDefinition(MachineDefinition, ResourceDefinition):
    """
    Definition of a Google Compute Engine machine.
    """
    @classmethod
    def get_type(cls):
        return "gce"

    def __init__(self, xml, config):
        MachineDefinition.__init__(self, xml, config)
        x = xml.find("attrs/attr[@name='gce']/attrs")
        assert x is not None
        self.copy_option(x, 'machineName', str)

        self.copy_option(x, 'region', str)
        self.copy_option(x, 'instanceType', str, empty = False)
        self.copy_option(x, 'project', str)
        self.copy_option(x, 'serviceAccount', str)
        self.copy_option(x, 'canIpForward', bool, optional=True)
        self.access_key_path = self.get_option_value(x, 'accessKey', str)

        self.copy_option(x, 'tags', 'strlist')
        self.metadata = { k.get("name"): k.find("string").get("value")
                          for k in x.findall("attr[@name='metadata']/attrs/attr") }

        scheduling = x.find("attr[@name='scheduling']")
        self.copy_option(scheduling, 'automaticRestart', bool)
        self.copy_option(scheduling, 'preemptible', bool)
        self.copy_option(scheduling, 'onHostMaintenance', str)

        instance_service_account = x.find("attr[@name='instanceServiceAccount']")
        self.copy_option(instance_service_account, "email", str)
        self.copy_option(instance_service_account, "scopes", 'strlist')

        self.ipAddress = self.get_option_value(x, 'ipAddress', 'resource', optional = True)
        self.copy_option(x, 'network', 'resource', optional = True)
        self.copy_option(x, 'subnet', str, optional = True)
        self.labels = { k.get("name"): k.find("string").get("value")
                        for k in x.findall("attr[@name='labels']/attrs/attr") }

        def opt_disk_name(dname):
            return ("{0}-{1}".format(self.machine_name, dname) if dname is not None else None)

        def parse_block_device(xml):
            result = {
                'disk': self.get_option_value(xml, 'disk', 'resource', optional = True),
                'disk_name': opt_disk_name(self.get_option_value(xml, 'disk_name', str, optional = True)),
                'snapshot': self.get_option_value(xml, 'snapshot', str, optional = True),
                'image': self.get_option_value(xml, 'image', 'resource', optional = True),
                'size': self.get_option_value(xml, 'size', int, optional = True),
                'type': self.get_option_value(xml, 'diskType', str),
                'deleteOnTermination': self.get_option_value(xml, 'deleteOnTermination', bool),
                'readOnly': self.get_option_value(xml, 'readOnly', bool),
                'bootDisk': self.get_option_value(xml, 'bootDisk', bool),
                'encrypt': self.get_option_value(xml, 'encrypt', bool),
                'passphrase': self.get_option_value(xml, 'passphrase', str)
            }
            if not(result['disk'] or result['disk_name']):
                raise Exception("{0}: blockDeviceMapping item must specify either an "
                                "external disk name to mount or a disk name to create"
                                .format(self.machine_name))
            return result

        self.block_device_mapping = { k.get("name"): parse_block_device(k)
                                      for k in x.findall("attr[@name='blockDeviceMapping']/attrs/attr") }

        boot_devices = [k for k,v in self.block_device_mapping.iteritems() if v['bootDisk']]
        if len(boot_devices) == 0:
            raise Exception("machine {0} must have a boot device.".format(self.name))
        if len(boot_devices) > 1:
            raise Exception("machine {0} must have exactly one boot device.".format(self.name))


    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region or "???")


class GCEState(MachineState, ResourceState):
    """
    State of a Google Compute Engine machine.
    """
    @classmethod
    def get_type(cls):
        return "gce"

    machine_name = attr_property("gce.name", None)
    public_ipv4 = attr_property("publicIpv4", None)
    private_ipv4 = attr_property("privateIpv4", None)

    region = attr_property("gce.region", None)
    instance_type = attr_property("gce.instanceType", None)

    can_ip_forward = attr_property("gce.canIpForward", False)

    public_client_key = attr_property("gce.publicClientKey", None)
    private_client_key = attr_property("gce.privateClientKey", None)

    public_host_key = attr_property("gce.publicHostKey", None)
    private_host_key = attr_property("gce.privateHostKey", None)

    tags = attr_property("gce.tags", None, 'json')
    metadata = attr_property("gce.metadata", {}, 'json')
    labels = attr_property("gce.labels", {}, 'json')
    email = attr_property("gce.serviceAccountEmail", 'default')
    scopes = attr_property("gce.serviceAccountScopes", [], 'json')
    automatic_restart = attr_property("gce.scheduling.automaticRestart", None, bool)
    preemptible = attr_property("gce.scheduling.preemptible", None, bool)
    on_host_maintenance = attr_property("gce.scheduling.onHostMaintenance", None)
    ipAddress = attr_property("gce.ipAddress", None)
    network = attr_property("gce.network", None)
    subnet = attr_property("gce.subnet", None)

    block_device_mapping = attr_property("gce.blockDeviceMapping", {}, 'json')

    backups = nixops.util.attr_property("gce.backups", {}, 'json')

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._conn = None

    @property
    def resource_id(self):
        return self.machine_name

    def show_type(self):
        s = super(GCEState, self).show_type()
        if self.region: s = "{0} [{1}; {2}]".format(s, self.region, self.instance_type)
        return s

    credentials_prefix = "deployment.gce"

    @property
    def full_name(self):
        return "GCE machine '{0}'".format(self.machine_name)

    def node(self):
       return self.connect().ex_get_node(self.machine_name, self.region)

    def address_to(self, resource):
        """Return the IP address to be used to access "resource" from this machine."""
        if isinstance(resource, GCEState) and resource.network == self.network:
            return resource.private_ipv4
        else:
            return MachineState.address_to(self, resource)

    def full_metadata(self, metadata):
        result = metadata.copy()
        result.update({
            'sshKeys': "root:{0}".format(self.public_client_key),
            'ssh_host_{0}_key'.format(self.host_key_type): self.private_host_key,
            'ssh_host_{0}_key_pub'.format(self.host_key_type): self.public_host_key
        })
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
        if not self.depl.logger.confirm("are you sure you want to destroy GCE disk '{0}'?".format(volume_id)):
            if allow_keep:
                return
            else:
                raise Exception("not destroying GCE disk '{0}'".format(volume_id))
        self.log("destroying GCE disk '{0}'...".format(volume_id))
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

    defn_properties = ['tags', 'region', 'instance_type',
                       'email', 'scopes', 'subnet', 'preemptible',
                       'metadata', 'ipAddress', 'network']

    def is_deployed(self):
        return (self.vm_id or self.block_device_mapping)

    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, GCEDefinition)

        self.no_project_change(defn)
        self.no_region_change(defn)
        self.no_change(self.machine_name != defn.machine_name, "instance name")

        self.set_common_state(defn)
        self.copy_credentials(defn)
        self.machine_name = defn.machine_name
        self.region = defn.region

        if not self.public_client_key:
            (private, public) = create_key_pair()
            self.public_client_key = public
            self.private_client_key = private

        self.host_key_type = "ed25519" if self.state_version != "14.12" and nixops.util.parse_nixos_version(defn.config["nixosRelease"]) >= ["15", "09"] else "ecdsa"

        if not self.public_host_key:
            (private, public) = create_key_pair(type=self.host_key_type)
            self.public_host_key = public
            self.private_host_key = private

        recreate = False

        if check:
            try:
                node = self.node()
                if self.vm_id:

                    if node.state == NodeState.TERMINATED:
                        recreate = True
                        self.warn("the instance is terminated and needs a reboot")
                        self.state = self.STOPPED

                    self.handle_changed_property('region', node.extra['zone'].name, can_fix = False)
                    self.handle_changed_property('preemptible', node.extra['scheduling']['preemptible'], can_fix = False)

                    # a bit hacky but should work
                    network_name = node.extra['networkInterfaces'][0]['network'].split('/')[-1]
                    if network_name == 'default': network_name = None
                    self.handle_changed_property('network', network_name)

                    self.handle_changed_property('instance_type', node.size)
                    self.handle_changed_property('public_ipv4',
                                                 node.public_ips[0] if node.public_ips else None,
                                                 property_name = 'public IP address')
                    if self.public_ipv4:
                        known_hosts.add(self.public_ipv4, self.public_host_key)

                    self.handle_changed_property('private_ipv4',
                                                 node.private_ips[0] if node.private_ips else None,
                                                 property_name = 'private IP address')

                    if self.ipAddress:
                        try:
                            address = self.connect().ex_get_address(self.ipAddress)
                            if self.public_ipv4 and self.public_ipv4 != address.address:
                                self.warn("static IP Address {0} assigned to this machine has unexpectely "
                                          "changed from {1} to {2} most likely due to being redeployed"
                                          .format(self.ipAddress, self.public_ipv4, address.address) )
                                self.ipAddress = None

                        except libcloud.common.google.ResourceNotFoundError:
                            self.warn("static IP Address resource {0} used by this machine has been destroyed; "
                                      "it is likely that the machine is still holding the address itself ({1}) "
                                      "and this is your last chance to reclaim it before it gets "
                                      "lost in a reboot".format(self.ipAddress, self.public_ipv4) )

                    self.handle_changed_property('tags', sorted(node.extra['tags']))

                    actual_metadata = { i['key']: i['value']
                                        for i in node.extra['metadata'].get('items', [])
                                        if i['key'] not in [ 'ssh_host_{0}_key'.format(self.host_key_type), 'sshKeys',
                                                             'ssh_host_{0}_key_pub'.format(self.host_key_type)] }
                    self.handle_changed_property('metadata', actual_metadata)

                    self.handle_changed_property('automatic_restart',
                                                 node.extra['scheduling']["automaticRestart"])
                    self.handle_changed_property('on_host_maintenance',
                                                 node.extra['scheduling']["onHostMaintenance"])

                    attached_disk_names = [d.get("deviceName", None) for d in node.extra['disks'] ]
                    # check that all disks are attached
                    for k, v in self.block_device_mapping.iteritems():
                        disk_name = v['disk_name'] or v['disk']
                        is_attached = disk_name in attached_disk_names
                        if not is_attached  and not v.get('needsAttach', False):
                            self.warn("disk {0} seems to have been detached behind our back; will reattach...".format(disk_name))
                            v['needsAttach'] = True
                            self.update_block_device_mapping(k, v)
                        if is_attached and v.get('needsAttach', False):
                            self.warn("disk {0} seems to have been attached for us; thank you, mr. Elusive Bug!".format(disk_name))
                            del v['needsAttach']
                            self.update_block_device_mapping(k, v)

                    # check that no extra disks are attached
                    defn_disk_names  = [v['disk_name'] or v['disk'] for k,v in defn.block_device_mapping.iteritems()]
                    state_disk_names = [v['disk_name'] or v['disk'] for k,v in self.block_device_mapping.iteritems()]
                    unexpected_disks = list( set(attached_disk_names) - set(defn_disk_names) - set(state_disk_names) )
                    if unexpected_disks:
                        self.warn("unexpected disk(s) {0} are attached to this instance; "
                                  "not fixing this just in case".format(unexpected_disks))
                else:
                    self.warn_not_supposed_to_exist(valuable_data = True)
                    self.confirm_destroy(node, self.full_name)

            except libcloud.common.google.ResourceNotFoundError:
                if self.vm_id:
                    self.warn("the instance seems to have been destroyed behind our back")
                    if not allow_recreate: raise Exception("use --allow-recreate to fix")
                    self._node_deleted()

            # check that the disks that should exist do exist
            # and that the disks we expected to create don't exist yet
            for k,v in defn.block_device_mapping.iteritems():
                disk_name = v['disk_name'] or v['disk']
                try:
                    disk = self.connect().ex_get_volume(disk_name, v.get('region', None) )
                    if k not in self.block_device_mapping and v['disk_name']:
                        self.warn_not_supposed_to_exist(resource_name = disk_name, valuable_data = True)
                        self.confirm_destroy(disk, disk_name)

                except libcloud.common.google.ResourceNotFoundError:
                    if v['disk']:
                        raise Exception("external disk '{0}' is required but doesn't exist".format(disk_name))
                    if k in self.block_device_mapping and v['disk_name']:
                        self.warn("disk '{0}' is supposed to exist, but is missing; will recreate...".format(disk_name))
                        self.update_block_device_mapping(k, None)

        # create missing disks
        for k, v in defn.block_device_mapping.iteritems():
            if k in self.block_device_mapping: continue
            if v['disk'] is None:
                extra_msg = ( " from snapshot '{0}'".format(v['snapshot']) if v['snapshot']
                         else " from image '{0}'".format(v['image'])       if v['image']
                         else "" )
                self.log("creating GCE disk of {0} GiB{1}..."
                         .format(v['size'] if v['size'] else "auto", extra_msg))
                v['region'] = defn.region
                try:
                    self.connect().create_volume(v['size'], v['disk_name'], v['region'],
                                                snapshot=v['snapshot'], image=v['image'],
                                                ex_disk_type="pd-" + v.get('type', 'standard'),
                                                use_existing=False)
                except AttributeError:
                    # libcloud bug: The region we're trying to create the disk
                    # in doesn't exist.
                    raise Exception("tried creating a disk in nonexistent "
                                    "region %r" % v['region'])
                except libcloud.common.google.ResourceExistsError:
                    raise Exception("tried creating a disk that already exists; "
                                    "please run 'deploy --check' to fix this")
            v['needsAttach'] = True
            self.update_block_device_mapping(k, v)

        if self.vm_id:
            if self.instance_type != defn.instance_type:
                recreate = True
                self.warn("change of the instance type requires a reboot")

            if self.network != defn.network:
                raise Exception("change of network is currently not supported")

            if self.subnet != defn.subnet:
                raise Exception("change of subnet is currently not supported")

            if self.email != defn.email or self.scopes != defn.scopes:
                recreate = True
                self.warn('change of service account requires a reboot')

            for k, v in self.block_device_mapping.iteritems():
                defn_v = defn.block_device_mapping.get(k, None)
                if defn_v and not v.get('needsAttach', False):
                    if v['bootDisk'] != defn_v['bootDisk']:
                        recreate = True
                        self.warn("change of the boot disk requires a reboot")
                    if v['readOnly'] != defn_v['readOnly']:
                        recreate = True
                        self.warn("remounting disk as ro/rw requires a reboot")

        if recreate:
            if not allow_reboot:
                raise Exception("reboot is required for the requested changes; please run with --allow-reboot")
            self.stop()

        self.create_node(defn)
        if self.node().state == NodeState.STOPPED:
            self.start()

    def create_node(self, defn):

        if not self.vm_id:
            self.log("creating {0}...".format(self.full_name))
            boot_disk = next((v for k,v in defn.block_device_mapping.iteritems() if v.get('bootDisk', False)), None)
            if not boot_disk:
                raise Exception("no boot disk found for {0}".format(self.full_name))
            try:
                service_accounts = []
                account = { 'email': defn.email }
                if defn.scopes != []:
                    account['scopes'] = defn.scopes
                service_accounts.append(account)
                # keeping a gcloud like behavior, if nothing was specified
                # i.e service account is default get the default scopes as well
                if defn.email == 'default' and defn.scopes == []: service_accounts=None

                node = self.connect().create_node(self.machine_name, defn.instance_type, "",
                                 ex_preemptible = (defn.preemptible if defn.preemptible else None),
                                 location = self.connect().ex_get_zone(defn.region),
                                 ex_boot_disk = self.connect().ex_get_volume(boot_disk['disk_name'] or boot_disk['disk'], boot_disk.get('region', None)),
                                 ex_metadata = self.full_metadata(defn.metadata), ex_tags = defn.tags, ex_service_accounts = service_accounts,
                                 external_ip = (self.connect().ex_get_address(defn.ipAddress) if defn.ipAddress else 'ephemeral'),
                                 ex_can_ip_forward = defn.can_ip_forward,
                                 # in theory the API accepts creating an
                                 # instance by specifying only the subnet
                                 # but this seems to be a libcloud issue
                                 # where it doesn't accept None for
                                 # ex_network argument.
                                 ex_network = (defn.network if defn.network else 'default'),
                                 ex_subnetwork = (defn.subnet if defn.subnet is not None else None) )
            except libcloud.common.google.ResourceExistsError:
                raise Exception("tried creating an instance that already exists; "
                                "please run 'deploy --check' to fix this")
            self.vm_id = self.machine_name
            self.state = self.STARTING
            self.ssh_pinged = False
            self.copy_properties(defn)
            self.public_ipv4 = node.public_ips[0]
            self.log("got public IP: {0}".format(self.public_ipv4))
            known_hosts.add(self.public_ipv4, self.public_host_key)
            self.private_ipv4 = node.private_ips[0]
            for k,v in self.block_device_mapping.iteritems():
                v['needsAttach'] = True
                self.update_block_device_mapping(k, v)
            # set scheduling config here instead of triggering an update using None values
            # because we might be called with defn = self, thus modifying self would ruin defn
            self.connect().ex_set_node_scheduling(node,
                                                  automatic_restart = defn.automatic_restart,
                                                  on_host_maintenance = defn.on_host_maintenance)
            self.automatic_restart = defn.automatic_restart
            self.on_host_maintenance = defn.on_host_maintenance

        # Update instance type
        if self.instance_type != defn.instance_type:
            self.connect().ex_set_machine_type(self.node(), defn.instance_type)
            self.instance_type = defn.instance_type

        # Update service account
        if self.email != defn.email or self.scopes != defn.scopes:
            self.log('updating the service account')
            node = self.node()
            request = '/zones/%s/instances/%s/setServiceAccount' % (node.extra['zone'].name, node.name)
            service_account = {}
            service_account["email"] = defn.email
            if defn.scopes != []: service_account["scopes"] = defn.scopes
            self.connect().connection.async_request(request, method='POST', data=service_account)
            self.email = defn.email
            self.scopes = defn.scopes

        # Apply labels to node and disks just created
        if self.labels != defn.labels:
            self.log('updating node labels')
            node = self.node()
            labels_request = "/zones/%s/instances/%s" % (node.extra['zone'].name, node.name)
            response = self.connect().connection.request(labels_request, method='GET').object
            body = { 'labels': defn.labels, 'labelFingerprint': response['labelFingerprint']}
            request = '/zones/%s/instances/%s/setLabels' % (node.extra['zone'].name, node.name)
            self.connect().connection.async_request(request, method='POST', data=body)
            self.labels = defn.labels
            self.log('updating disks labels')
            for k, v in self.block_device_mapping.items():
                disk_name = v['disk_name']
                if not (('disk' in disk_name or 'part' in disk_name)
                        and (disk_name.startswith(node.name))): continue
                disk_labels_request = "/zones/%s/disks/%s" % (node.extra['zone'].name, disk_name)
                response = self.connect().connection.request(disk_labels_request, method='GET').object
                body = { 'labels': defn.labels, 'labelFingerprint': response['labelFingerprint']}
                request = '/zones/%s/disks/%s/setLabels' % (node.extra['zone'].name, disk_name)
                self.connect().connection.async_request(request, method='POST', data=body)

        # Attach missing volumes
        for k, v in self.block_device_mapping.items():
            defn_v = defn.block_device_mapping.get(k, None)
            if v.get('needsAttach', False) and defn_v:
                disk_name = v['disk_name']
                disk_volume = v['disk_name'] if v['disk'] is None else v['disk']
                disk_region = v.get('region', None)
                v['readOnly'] = defn_v['readOnly']
                v['bootDisk'] = defn_v['bootDisk']
                v['deleteOnTermination'] = defn_v['deleteOnTermination']
                v['passphrase'] = defn_v['passphrase']
                self.log("attaching GCE disk '{0}'...".format(disk_name))
                if not v.get('bootDisk', False):
                    self.connect().attach_volume(self.node(), self.connect().ex_get_volume(disk_volume, disk_region),
                                   device = disk_name,
                                   ex_mode = ('READ_ONLY' if v['readOnly'] else 'READ_WRITE'))
                del v['needsAttach']
                self.update_block_device_mapping(k, v)

            # generate LUKS key if the model didn't specify one
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") == "":
                v['generatedKey'] = generate_random_string(length=256)
                self.update_block_device_mapping(k, v)

        if self.metadata != defn.metadata:
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
            self.log('updating tags')
            self.connect().ex_set_node_tags(self.node(), defn.tags)
            self.tags = defn.tags

        if self.public_ipv4 and self.ipAddress != defn.ipAddress:
            self.log("detaching old public IP address {0}".format(self.public_ipv4))
            self.connect().connection.async_request(
                "/zones/{0}/instances/{1}/deleteAccessConfig?accessConfig=External+NAT&networkInterface=nic0"
                .format(self.region, self.machine_name), method = 'POST')
            self.public_ipv4 = None
            self.ipAddress = None

        if self.public_ipv4 is None:
            self.log("attaching public IP address {0}".format(defn.ipAddress or "[Ephemeral]"))
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
            self.log("got public IP: {0}".format(self.public_ipv4))
            known_hosts.add(self.public_ipv4, self.public_host_key)
            self.ssh.reset()
            self.ssh_pinged = False

        if self.automatic_restart != defn.automatic_restart or self.on_host_maintenance != defn.on_host_maintenance:
            self.log("setting scheduling configuration")
            self.connect().ex_set_node_scheduling(self.node(),
                                                  automatic_restart = defn.automatic_restart,
                                                  on_host_maintenance = defn.on_host_maintenance)
            self.automatic_restart = defn.automatic_restart
            self.on_host_maintenance = defn.on_host_maintenance


    def reboot(self, hard=False):
        if hard:
            self.log("sending hard reset to GCE machine...")
            self.node().reboot()
            self.state = self.STARTING
        else:
            MachineState.reboot(self, hard=hard)


    def start(self):
        if self.vm_id:
            try:
                node = self.node()
            except libcloud.common.google.ResourceNotFoundError:
                self.warn("seems to have been destroyed already")
                self._node_deleted()
                node = None

            if node and (node.state == NodeState.TERMINATED):
                self.stop()

            if node and (node.state == NodeState.STOPPED):
                self.log("starting GCE machine")
                self.connect().ex_start_node(node)
                self.public_ipv4 = self.node().public_ips[0]
                self.private_ipv4 = self.node().private_ips[0]
                known_hosts.add(self.public_ipv4, self.public_host_key)
                self.wait_for_ssh(check=True)
                self.send_keys()

        if not self.vm_id and self.block_device_mapping:
            prev_public_ipv4 = self.public_ipv4
            prev_private_ipv4 = self.private_ipv4
            self.create_node(self)
            if prev_public_ipv4 != self.public_ipv4:
                self.warn("Public IP address has changed from {0} to {1}, "
                          "you may need to run 'nixops deploy'"
                          .format(prev_public_ipv4, self.public_ipv4) )
            if prev_private_ipv4 != self.private_ipv4:
                self.warn("Private IP address has changed from {0} to {1}, "
                          "you may need to run 'nixops deploy'"
                          .format(prev_private_ipv4, self.private_ipv4) )
            self.wait_for_ssh(check=True)
            self.send_keys()


    def stop(self):
        if not self.vm_id: return

        try:
            node = self.node()
        except libcloud.common.google.ResourceNotFoundError:
            self.warn("seems to have been destroyed already")
            self._node_deleted()
            return

        if node.state != NodeState.TERMINATED:
            self.log_start("stopping GCE machine... ")
            self.connect().ex_stop_node(node)
            self.state = self.STOPPING

            def check_stopped():
                return self.node().state == NodeState.STOPPED
            if nixops.util.check_wait(check_stopped, initial=3, max_tries=100, exception=False): # = 5 min
                self.log_end("stopped")
            else:
                self.log_end("(timed out)")

        self.state = self.STOPPED
        self.ssh.reset()

    def destroy(self, wipe=False):
        if wipe:
            self.depl.logger.warn("wipe is not supported")

        if not self.project:
            return True

        if self.state == self.MISSING:
            # The machine is down, we have nothing to do.
            return True

        try:
            node = self.node()
            question = "are you sure you want to destroy {0}?"
            if not self.depl.logger.confirm(question.format(self.full_name)):
                return False

            known_hosts.remove(self.public_ipv4, self.public_host_key)
            self.log("destroying the GCE machine...")
            node.destroy()

        except libcloud.common.google.ResourceNotFoundError:
            self.warn("seems to have been destroyed already")
        self._node_deleted()

        # Destroy volumes created for this instance.
        for k, v in self.block_device_mapping.items():
            if v.get('deleteOnTermination', False):
                self._delete_volume(v['disk_name'], v['region'], True)
            self.update_block_device_mapping(k, None)

        return True


    def after_activation(self, defn):
        # Detach volumes that are no longer in the deployment spec.
        for k, v in self.block_device_mapping.items():
            if k not in defn.block_device_mapping:
                disk_name = v['disk'] or v['disk_name']

                self.log("unmounting device '{0}'...".format(disk_name))
                if v.get('encrypt', False):
                    dm = "/dev/mapper/{0}".format(disk_name)
                    self.run_command("umount -l {0}".format(dm), check=False)
                    self.run_command("cryptsetup luksClose {0}".format(dm), check=False)
                else:
                    self.run_command("umount -l {0}".format(k), check=False)

                node = self.node()
                try:
                    if not v.get('needsAttach', False):
                        self.log("detaching GCE disk '{0}'...".format(disk_name))
                        volume = self.connect().ex_get_volume(disk_name, v.get('region', None) )
                        self.connect().detach_volume(volume, node)
                        v['needsAttach'] = True
                        self.update_block_device_mapping(k, v)

                    if v.get('deleteOnTermination', False):
                        self._delete_volume(disk_name, v['region'])
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn("GCE disk '{0}' seems to have been already destroyed".format(disk_name))

                self.update_block_device_mapping(k, None)


    def get_console_output(self):
        node = self.node()
        if node.state == NodeState.TERMINATED:
          raise Exception("cannot get console output of a state=TERMINATED machine '{0}'".format(self.name))
        request = '/zones/%s/instances/%s/serialPort' % (node.extra['zone'].name, node.name)
        return self.connect().connection.request(request, method='GET').object['contents']


    def _check(self, res):
        try:
            node = self.node()
            res.exists = True
            res.is_up = node.state == NodeState.RUNNING or node.state == NodeState.REBOOTING
            if node.state == NodeState.REBOOTING or node.state == NodeState.PENDING: self.state = self.STARTING
            if node.state == NodeState.STOPPED or node.state == NodeState.TERMINATED: self.state = self.STOPPED
            if node.state == NodeState.UNKNOWN: self.state = self.UNKNOWN
            if node.state == NodeState.RUNNING:
                # check that all disks are attached
                res.disks_ok = True
                for k, v in self.block_device_mapping.iteritems():
                    disk_name = v['disk_name'] or v['disk']
                    if all(d.get("deviceName", None) != disk_name for d in node.extra['disks']):
                        res.disks_ok = False
                        res.messages.append("disk {0} is detached".format(disk_name))
                        # Try to get a disk; if we can't get it, then it's
                        # been destroyed.
                        try:
                            self.connect().ex_get_volume(disk_name, v.get('region', None))
                        except libcloud.common.google.ResourceNotFoundError:
                            res.messages.append("disk {0} is destroyed".format(disk_name))
                self.handle_changed_property('public_ipv4',
                                              node.public_ips[0] if node.public_ips else None,
                                              property_name = 'public IP address')
                if self.public_ipv4:
                    known_hosts.add(self.public_ipv4, self.public_host_key)

                self.handle_changed_property('private_ipv4',
                                              node.private_ips[0] if node.private_ips else None,
                                              property_name = 'private IP address')

                MachineState._check(self, res)

        except libcloud.common.google.ResourceNotFoundError:
            res.exists = False
            res.is_up = False
            self.vm_id = None
            self.state = self.MISSING;

    def create_after(self, resources, defn):
        # Just a check for all GCE resource classes
        return {r for r in resources if
                isinstance(r, nixops.resources.gce_static_ip.GCEStaticIPState) or
                isinstance(r, nixops.resources.gce_disk.GCEDiskState) or
                isinstance(r, nixops.resources.gce_image.GCEImageState) or
                isinstance(r, nixops.resources.gce_network.GCENetworkState)}


    def backup(self, defn, backup_id, devices=[]):
        self.log("backing up {0} using ID '{1}'".format(self.full_name, backup_id))

        if sorted(defn.block_device_mapping.keys()) != sorted(self.block_device_mapping.keys()):
            self.warn("the list of disks currently deployed doesn't match the current deployment"
                     " specification; consider running 'deploy' first; the backup may be incomplete")

        backup = {}
        _backups = self.backups
        for k, v in self.block_device_mapping.iteritems():
            disk_name = v['disk_name'] or v['disk']
            if devices == [] or k in devices or disk_name in devices:
                volume = self.connect().ex_get_volume(disk_name, v.get('region', None))
                snapshot_name = "backup-{0}-{1}".format(backup_id, disk_name[-32:])
                self.log("initiating snapshotting of disk '{0}': '{1}'".format(disk_name, snapshot_name))
                self.connect().connection.request(
                    '/zones/%s/disks/%s/createSnapshot'
                        %(volume.extra['zone'].name, volume.name),
                    method = 'POST', data = {
                        'name': snapshot_name,
                        'description': "backup of disk {0} attached to {1}"
                                        .format(volume.name, self.machine_name)
                    })

                # Apply labels to snapshot just created
                self.wait_for_snapshot_initiated(snapshot_name)

                if defn.labels:
                    self.log("updating labels of snapshot '{0}'".format(snapshot_name))
                    self.connect().connection.request(
                        '/global/snapshots/%s/setLabels' %(snapshot_name),
                        method = 'POST', data = {
                            'labels': defn.labels,
                            'labelFingerprint':
                                self.connect().connection.request("/global/snapshots/{0}".format(snapshot_name), method='GET').object['labelFingerprint']
                    })

                backup[k] = snapshot_name
            _backups[backup_id] = backup
            self.backups = _backups

    def wait_for_snapshot_initiated(self, snapshot_name):
        while True:
            try:
                snapshot = self.connect().ex_get_snapshot(snapshot_name)
                if snapshot.status in "READY" "CREATING" "UPLOADING":
                    self.log_end(" done")
                    break
                else:
                    raise Exception("snapshot '{0}' is in an unexpected state {1}".format(snapshot_name, snapshot.status))
            except libcloud.common.google.ResourceNotFoundError:
                self.log_continue(".")
                time.sleep(1)

    def restore(self, defn, backup_id, devices=[]):
        self.log("restoring {0} to backup '{1}'".format(self.full_name, backup_id))

        self.stop()

        for k, v in self.block_device_mapping.items():
            disk_name = v['disk_name'] or v['disk']
            s_id = self.backups[backup_id].get(disk_name, None)
            if s_id and (devices == [] or k in devices or disk_name in devices):
                try:
                    snapshot = self.connect().ex_get_snapshot(s_id)
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn("snapsnot {0} for disk {1} is missing; skipping".format(s_id, disk_name))
                    continue

                try:
                    self.log("destroying disk {0}".format(disk_name))
                    self.connect().ex_get_volume(disk_name, v.get('region', None)).destroy()
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn("disk {0} seems to have been destroyed already".format(disk_name))

                self.log("creating disk {0} from snapshot '{1}'".format(disk_name, s_id))
                self.connect().create_volume(None, disk_name, v.get('region', None),
                                             ex_disk_type = "pd-" + v.get('type', 'standard'),
                                             snapshot = snapshot, use_existing= False)

    def remove_backup(self, backup_id, keep_physical=False):
        self.log('removing backup {0}'.format(backup_id))
        _backups = self.backups
        if not backup_id in _backups.keys():
            self.warn('backup {0} not found; skipping'.format(backup_id))
        else:
            for d_name, snapshot_id in _backups[backup_id].iteritems():
                try:
                    self.log('removing snapshot {0}'.format(snapshot_id))
                    self.connect().ex_get_snapshot(snapshot_id).destroy()
                except libcloud.common.google.ResourceNotFoundError:
                    self.warn('snapshot {0} not found; skipping'.format(snapshot_id))

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
                    info.append("{0} - {1} - not available in backup".format(self.name, disk_name))
                else:
                    snapshot_id = snapshots[disk_name]
                    try:
                        snapshot = self.connect().ex_get_snapshot(snapshot_id)
                        if snapshot.status != 'READY':
                            backup_status = "running"
                    except libcloud.common.google.ResourceNotFoundError:
                        info.append("{0} - {1} - {2} - snapshot has disappeared".format(self.name, disk_name, snapshot_id))
                        backup_status = "unavailable"
            for d_name, s_id in snapshots.iteritems():
                if not any(d_name == v['disk_name'] or d_name == v['disk'] for k,v in self.block_device_mapping.iteritems()):
                    info.append("{0} - {1} - {2} - a snapshot of a disk that is not or no longer deployed".format(self.name, d_name, s_id))
            backups[b_id]['status'] = backup_status
            backups[b_id]['info'] = info
        return backups


    def get_physical_spec(self):
        block_device_mapping = {}
        for k, v in self.block_device_mapping.items():
            if (v.get('encrypt', False)
                and v.get('passphrase', "") == ""
                and v.get('generatedKey', "") != ""):
                block_device_mapping[k] = {
                    'passphrase': Call(RawValue("pkgs.lib.mkOverride 10"), v['generatedKey']),
                }

        return {
            'imports': [
                RawValue("<nixpkgs/nixos/modules/virtualisation/google-compute-config.nix>")
            ],
            ('deployment', 'gce', 'blockDeviceMapping'): block_device_mapping,
            ('environment', 'etc', 'default/instance_configs.cfg', 'text'): '[InstanceSetup]\nset_host_keys = false',
        }

    def get_physical_backup_spec(self, backupid):
          val = {}
          if backupid in self.backups:
              for dev, snap in self.backups[backupid].items():
                  val[dev] = { 'snapshot': Call(RawValue("pkgs.lib.mkOverride 10"), snap)}
              val = { ('deployment', 'gce', 'blockDeviceMapping'): val }
          else:
              val = RawValue("{{}} /* No backup found for id '{0}' */".format(backupid))
          return Function("{ config, pkgs, ... }", val)

    def get_keys(self):
        keys = MachineState.get_keys(self)
        # Ugly: we have to add the generated keys because they're not
        # there in the first evaluation (though they are present in
        # the final nix-build).
        for k, v in self.block_device_mapping.items():
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") != "":
                key_name = "luks-" + (v['disk_name'] or v['disk'])
                keys[key_name] = { 'text': v['generatedKey'], 'keyFile': '/run/keys' + key_name, 'destDir': '/run/keys', 'group': 'root', 'permissions': '0600', 'user': 'root'}
        return keys

    def get_ssh_name(self):
        if not self.public_ipv4:
            raise Exception("{0} does not have a public IPv4 address (yet)".format(self.full_name))
        return self.public_ipv4

    def get_ssh_private_key_file(self):
        return self._ssh_private_key_file or self.write_ssh_private_key(self.private_client_key)

    def get_ssh_flags(self, *args, **kwargs):
        super_flags = super(GCEState, self).get_ssh_flags(*args, **kwargs)
        return super_flags + ["-i", self.get_ssh_private_key_file()]
