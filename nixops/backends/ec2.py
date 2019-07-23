# -*- coding: utf-8 -*-

from __future__ import absolute_import, print_function

import os
import os.path
import sys
import re
import time
import math
import shutil
import calendar
import boto.ec2
import boto.ec2.blockdevicemapping
import boto.ec2.networkinterface
import botocore.exceptions

from . import MachineDefinition, MachineState
from ..nix_expr import Function, Call, RawValue
from ..resources.ebs_volume import EBSVolumeState
from ..resources.elastic_ip import ElasticIPState
import nixops.resources.ec2_common
from ..util import device_name_to_boto_expected, device_name_stored_to_real, device_name_user_entered_to_stored
import nixops.ec2_utils
import nixops.known_hosts
import nixops.util
from xml import etree
import datetime
import boto3
from typing import Any, Dict, Optional, List, Iterable
from ..ec2_utils import key_value_to_ec2_key_value
from xml.etree.ElementTree import Element


class EC2InstanceDisappeared(Exception):
    pass

# name conventions:
# device - device name that user enters: sd, xvd or nvme
# device_stored - device name stored in db: sd or nvme
# device_real - device name attached to machine: xvd or nvme, sd can't be attached
# device_that_boto_expects - only sd device names can be passed to boto, but amazon will attach them as xvd or nvme based on machine type


class EC2Definition(MachineDefinition):
    """Definition of an EC2 machine."""

    @classmethod
    def get_type(cls):
        # type: () -> str
        return "ec2"

    def __init__(self, xml, config):
        # type: (Element, Dict[str, Any]) -> None
        super(EC2Definition, self).__init__(xml, config)

        self.profile = config["ec2"]["profile"]
        self.access_key_id = config["ec2"]["accessKeyId"]
        self.region = config["ec2"]["region"]
        self.zone = config["ec2"]["zone"]
        self.tenancy = config["ec2"]["tenancy"]
        self.ami = config["ec2"]["ami"]
        if self.ami == "":
            raise Exception("no AMI defined for EC2 machine ‘{0}’".format(self.name))
        self.instance_type = config["ec2"]["instanceType"]
        self.key_pair = config["ec2"]["keyPair"]
        self.private_key = config["ec2"]["privateKey"]
        self.security_groups = config["ec2"]["securityGroups"]
        self.placement_group = config["ec2"]["placementGroup"]
        self.instance_profile = config["ec2"]["instanceProfile"]
        self.tags = config["ec2"]["tags"]
        self.root_disk_size = config["ec2"]["ebsInitialRootDiskSize"]
        self.spot_instance_price = config["ec2"]["spotInstancePrice"]
        self.spot_instance_timeout = config["ec2"]["spotInstanceTimeout"]
        self.spot_instance_request_type = config["ec2"]["spotInstanceRequestType"]
        self.spot_instance_interruption_behavior = config["ec2"]["spotInstanceInterruptionBehavior"]
        self.ebs_optimized = config["ec2"]["ebsOptimized"]
        self.subnet_id = config["ec2"]["subnetId"]
        self.associate_public_ip_address = config["ec2"]["associatePublicIpAddress"]
        self.use_private_ip_address = config["ec2"]["usePrivateIpAddress"]
        self.source_dest_check = config["ec2"]["sourceDestCheck"]
        self.security_group_ids = config["ec2"]["securityGroupIds"]

        # convert sd to xvd because they are equal from aws perspective
        self.block_device_mapping = {device_name_user_entered_to_stored(k): v for k, v in config["ec2"]["blockDeviceMapping"].iteritems()}

        self.elastic_ipv4 = config["ec2"]["elasticIPv4"]

        self.dns_hostname = config["route53"]["hostName"].lower()
        self.dns_ttl = config["route53"]["ttl"]
        self.route53_access_key_id = config["route53"]["accessKeyId"]
        self.route53_use_public_dns_name = config["route53"]["usePublicDNSName"]
        self.route53_private = config["route53"]["private"]

    def show_type(self):
        # type: () -> str
        return "{0} [{1}]".format(self.get_type(), self.region or self.zone or "???")

    def host_key_type(self):
        # type: () -> str
        return "ed25519" if nixops.util.parse_nixos_version(self.config["nixosRelease"]) >= ["15", "09"] else "dsa"


class EC2State(MachineState, nixops.resources.ec2_common.EC2CommonState):
    """State of an EC2 machine."""

    @classmethod
    def get_type(cls):
        # type: () -> str
        return "ec2"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    # We need to store this in machine state so wait_for_ip knows what to wait for
    # Really it seems like this whole class should be parameterized by its definition.
    # (or the state shouldn't be doing the polling)
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)
    public_dns_name = nixops.util.attr_property("publicDnsName", None)
    use_private_ip_address = nixops.util.attr_property("ec2.usePrivateIpAddress", False, type=bool)
    source_dest_check = nixops.util.attr_property("ec2.sourceDestCheck", True, type=bool)
    associate_public_ip_address = nixops.util.attr_property("ec2.associatePublicIpAddress", False, type=bool)
    elastic_ipv4 = nixops.util.attr_property("ec2.elasticIpv4", None)
    profile = nixops.util.attr_property("ec2.profile", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    zone = nixops.util.attr_property("ec2.zone", None)
    tenancy = nixops.util.attr_property("ec2.tenancy", None)
    ami = nixops.util.attr_property("ec2.ami", None)
    instance_type = nixops.util.attr_property("ec2.instanceType", None)
    ebs_optimized = nixops.util.attr_property("ec2.ebsOptimized", None, bool)
    key_pair = nixops.util.attr_property("ec2.keyPair", None)
    public_host_key = nixops.util.attr_property("ec2.publicHostKey", None)
    private_host_key = nixops.util.attr_property("ec2.privateHostKey", None)
    private_key_file = nixops.util.attr_property("ec2.privateKeyFile", None)
    instance_profile = nixops.util.attr_property("ec2.instanceProfile", None)
    security_groups = nixops.util.attr_property("ec2.securityGroups", None, 'json')
    placement_group = nixops.util.attr_property("ec2.placementGroup", None, 'json')
    block_device_mapping = nixops.util.attr_property("ec2.blockDeviceMapping", {}, 'json')
    root_device_type = nixops.util.attr_property("ec2.rootDeviceType", None)
    backups = nixops.util.attr_property("ec2.backups", {}, 'json')
    dns_hostname = nixops.util.attr_property("route53.hostName", None)
    dns_ttl = nixops.util.attr_property("route53.ttl", None, int)
    route53_access_key_id = nixops.util.attr_property("route53.accessKeyId", None)
    client_token = nixops.util.attr_property("ec2.clientToken", None)
    spot_instance_request_id = nixops.util.attr_property("ec2.spotInstanceRequestId", None)
    spot_instance_price = nixops.util.attr_property("ec2.spotInstancePrice", None)
    subnet_id = nixops.util.attr_property("ec2.subnetId", None)
    first_boot = nixops.util.attr_property("ec2.firstBoot", True, type=bool)
    virtualization_type = nixops.util.attr_property("ec2.virtualizationType", None)

    def __init__(self, depl, name, id):
        # type: (EC2Definition, str, str) -> None
        super(EC2State, self).__init__(depl, name, id)

        self._session = None  # type: boto3.session.Session
        self._conn_route53 = None
        self._cached_instance = None

    def _reset_state(self):
        # type: () -> None

        """Discard all state pertaining to an instance."""
        with self.depl._db:
            self.state = MachineState.MISSING
            self.associate_public_ip_address = None
            self.use_private_ip_address = None
            self.source_dest_check = None
            self.vm_id = None
            self.public_ipv4 = None
            self.private_ipv4 = None
            self.public_dns_name = None
            self.elastic_ipv4 = None
            self.region = None
            self.zone = None
            self.tenancy = None
            self.ami = None
            self.instance_type = None
            self.ebs_optimized = None
            self.key_pair = None
            self.public_host_key = None
            self.private_host_key = None
            self.instance_profile = None
            self.security_groups = None
            self.placement_group = None
            self.tags = {}
            self.block_device_mapping = {}
            self.root_device_type = None
            self.backups = {}
            self.dns_hostname = None
            self.dns_ttl = None
            self.subnet_id = None

            self.client_token = None
            self.spot_instance_request_id = None
            self.spot_instance_price = None

    def get_ssh_name(self):
        # type: () -> str

        if self.use_private_ip_address:
            if not self.private_ipv4:
                raise Exception("EC2 machine '{0}' does not have a private IPv4 address (yet)".format(self.name))
            return self.private_ipv4
        else:
            if not self.public_ipv4:
                raise Exception("EC2 machine ‘{0}’ does not have a public IPv4 address (yet)".format(self.name))
            return self.public_ipv4

    def get_ssh_private_key_file(self):
        # type: () -> Optional[str]

        if self.private_key_file:
            return self.private_key_file

        if self._ssh_private_key_file:
            return self._ssh_private_key_file

        for r in self.depl.active_resources.itervalues():
            if isinstance(r, nixops.resources.ec2_keypair.EC2KeyPairState) and \
                    r.state == nixops.resources.ec2_keypair.EC2KeyPairState.UP and \
                    r.keypair_name == self.key_pair:
                return self.write_ssh_private_key(r.private_key)

        return None

    def get_ssh_flags(self, *args, **kwargs):
        # type: (*Any, **Any) -> List[str]

        file = self.get_ssh_private_key_file()
        super_flags = super(EC2State, self).get_ssh_flags(*args, **kwargs)

        return super_flags + (["-i", file] if file else [])

    def get_physical_spec(self):
        block_device_mapping = {}
        for device_stored, v in self.block_device_mapping.items():
            device_real = device_name_stored_to_real(device_stored)

            if (v.get('encrypt', False)
                and v.get('encryptionType', "luks") == "luks"
                and v.get('passphrase', "") == ""
                and v.get('generatedKey', "") != ""):
                block_device_mapping[device_real] = {
                    'passphrase': Call(RawValue("pkgs.lib.mkOverride 10"),
                                           v['generatedKey']),
                }

        return {
            'imports': [
                RawValue("<nixpkgs/nixos/modules/virtualisation/amazon-image.nix>")
            ],
            ('deployment', 'ec2', 'blockDeviceMapping'): block_device_mapping,
            ('deployment', 'ec2', 'instanceId'): self.vm_id,
            ('ec2', 'hvm'): self.virtualization_type == "hvm" or self.virtualization_type is None,
        }

    def get_physical_backup_spec(self, backupid):
        val = {}
        if backupid in self.backups:
            for device_stored, snap in self.backups[backupid].items():
                device_real = device_name_stored_to_real(device_stored)

                is_root_device = device_real.startswith("/dev/xvda") or device_real.startswith("/dev/nvme0")

                if not is_root_device:
                    val[device_real] = { 'disk': Call(RawValue("pkgs.lib.mkOverride 10"), snap)}
            val = { ('deployment', 'ec2', 'blockDeviceMapping'): val }
        else:
            val = RawValue("{{}} /* No backup found for id '{0}' */".format(backupid))
        return Function("{ config, pkgs, ... }", val)


    def get_keys(self):
        keys = MachineState.get_keys(self)
        # Ugly: we have to add the generated keys because they're not
        # there in the first evaluation (though they are present in
        # the final nix-build). Had to hardcode the default here to
        # make the old way of defining keys work.
        for device_stored, v in self.block_device_mapping.items():
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") != "" and v.get('encryptionType', "luks") == "luks":
                device_real = device_name_stored_to_real(device_stored)

                key_name = "luks-" + device_real.replace('/dev/', '')
                keys[key_name] = { 'text': v['generatedKey'], 'keyFile': '/run/keys/' + key_name, 'destDir': '/run/keys', 'group': 'root', 'permissions': '0600', 'user': 'root'}
        return keys


    def show_type(self):
        s = super(EC2State, self).show_type()
        if self.zone or self.region: s = "{0} [{1}; {2}]".format(s, self.zone or self.region, self.instance_type)
        return s


    @property
    def resource_id(self):
        return self.vm_id


    def address_to(self, m):
        if isinstance(m, EC2State): # FIXME: only if we're in the same region
            return m.private_ipv4
        return MachineState.address_to(self, m)

    def session(self):
        # type: () -> boto3.Session
        if not self._session:
            self._session = nixops.ec2_utils.session(**{
                "region_name": self.region,
                "profile_name": self.profile,
                "aws_access_key_id": self.access_key_id
            })

        return self._session

    def connect_route53(self):
        if self._conn_route53:
            return

        # Get the secret access key from the environment or from ~/.ec2-keys.
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.route53_access_key_id)

        self._conn_route53 = boto.connect_route53(access_key_id, secret_access_key)

    def _get_spot_instance_request_by_id(self, request_id, allow_missing=False):
        # type: (str, bool) -> Optional[Dict[str, Any]]
        """Get spot instance request object by id."""
        ec2 = self.session().client('ec2')
        try:
            result = ec2.describe_spot_instance_requests(SpotInstanceRequestsIds=[request_id])['SpotInstanceRequests']
        except botocore.exceptions.ClientError as e:
            if allow_missing and e.response['Error']['Code'] == "InvalidSpotInstanceRequestID.NotFound":
                result = []
            else:
                raise

        if len(result) == 0:
            if allow_missing:
                return None

            raise EC2InstanceDisappeared("Spot instance request ‘{0}’ disappeared!".format(request_id))

        return result[0]

    def _get_instance(self, instance_id=None, allow_missing=False, update=False):
        # type: (Optional[str], bool, bool) -> ...
        """Get instance object for this machine, with caching"""
        if not instance_id:
            instance_id = self.vm_id
        assert instance_id

        if not self._cached_instance:
            ec2 = self.session().resource('ec2')
            instance = ec2.Instance(instance_id)

            try:
                instance.load()
            except botocore.exceptions.ClientError as e:
                if allow_missing and e.response['Error']['Code'] == "InvalidInstanceID.NotFound":
                    instance = None
                else:
                    raise

            if not instance:
                if allow_missing:
                    return None

                raise EC2InstanceDisappeared("EC2 instance ‘{0}’ disappeared!".format(instance_id))

            self._cached_instance = instance

        elif update:
            self._cached_instance.reload()

        if self._cached_instance.launch_time:
            self.start_time = self._cached_instance.launch_time

        return self._cached_instance


    def _get_snapshot_by_id(self, snapshot_id):
        """Get snapshot object by instance id."""
        self.connect()
        snapshots = self._conn.get_all_snapshots([snapshot_id])
        if len(snapshots) != 1:
            raise Exception("unable to find snapshot ‘{0}’".format(snapshot_id))
        return snapshots[0]

    def _wait_for_ip(self):
        self.log_start("waiting for IP address... ".format(self.name))

        def _instance_ip_ready(ins):
            ready = True
            if self.associate_public_ip_address and not ins.public_ip_address:
                ready = False
            if self.use_private_ip_address and not ins.private_ip_address:
                ready = False
            return ready

        while True:
            instance = self._get_instance(update=True)
            self.log_continue("[{0}] ".format(instance.state['Name']))
            if instance.state['Name'] not in {"pending", "running", "scheduling", "launching", "stopped"}:
                raise Exception("EC2 instance ‘{0}’ failed to start (state is ‘{1}’)".format(self.vm_id, instance.state['Name']))
            if instance.state['Name'] != "running":
                time.sleep(3)
                continue
            if _instance_ip_ready(instance):
                break
            time.sleep(3)

        self.log_end("{0} / {1}".format(instance.public_ip_address, instance.private_ip_address))

        with self.depl._db:
            self.private_ipv4 = instance.private_ip_address
            self.public_ipv4 = instance.public_ip_address
            self.public_dns_name = instance.public_dns_name
            self.ssh_pinged = False

        nixops.known_hosts.update(self.public_ipv4, self._ip_for_ssh_key(), self.public_host_key)

    def _ip_for_ssh_key(self):
        if self.use_private_ip_address:
            return self.private_ipv4
        else:
            return self.public_ipv4

    def _booted_from_ebs(self):
        # type: () -> bool
        return self.root_device_type == "ebs"


    def update_block_device_mapping(self, k, v):
        x = self.block_device_mapping
        if v is None:
            x.pop(k, None)
        else:
            x[k] = v
        self.block_device_mapping = x


    def get_backups(self):
        if not self.region: return {}
        self.connect()
        backups = {}
        current_volumes = set([v['volumeId'] for v in self.block_device_mapping.values()])
        for b_id, b in self.backups.items():
            b = {device_name_stored_to_real(device): snap for device, snap in b.items()}
            backups[b_id] = {}
            backup_status = "complete"
            info = []
            for device_stored, v in self.block_device_mapping.items():
                device_real = device_name_stored_to_real(device_stored)

                snapshot_id = b.get(device_real, None)
                if snapshot_id is not None:
                    try:
                        snapshot = self._get_snapshot_by_id(snapshot_id)
                        snapshot_status = snapshot.update()
                        info.append("progress[{0},{1},{2}] = {3}".format(self.name, device_real, snapshot_id, snapshot_status))
                        if snapshot_status != '100%':
                            backup_status = "running"
                    except boto.exception.EC2ResponseError as e:
                        if e.error_code != "InvalidSnapshot.NotFound": raise
                        info.append("{0} - {1} - {2} - Snapshot has disappeared".format(self.name, device_real, snapshot_id))
                        backup_status = "unavailable"
            backups[b_id]['status'] = backup_status
            backups[b_id]['info'] = info
        return backups


    def remove_backup(self, backup_id, keep_physical=False):
        self.log('removing backup {0}'.format(backup_id))
        self.connect()
        _backups = self.backups
        if not backup_id in _backups.keys():
            self.warn('backup {0} not found, skipping'.format(backup_id))
        else:
            if not keep_physical:
                for dev, snapshot_id in _backups[backup_id].items():
                    snapshot = None
                    try:
                        snapshot = self._get_snapshot_by_id(snapshot_id)
                    except:
                        self.warn('snapshot {0} not found, skipping'.format(snapshot_id))
                    if not snapshot is None:
                        self.log('removing snapshot {0}'.format(snapshot_id))
                        self._retry(lambda: snapshot.delete())

            _backups.pop(backup_id)
            self.backups = _backups


    def backup(self, defn, backup_id, devices=[]):
        self.connect()

        self.log("backing up machine ‘{0}’ using id ‘{1}’".format(self.name, backup_id))
        backup = {}
        _backups = self.backups

        for device_stored, v in self.block_device_mapping.items():
            device_real = device_name_stored_to_real(device_stored)

            if devices == [] or device_real in devices:
                snapshot = self._retry(lambda: self._conn.create_snapshot(volume_id=v['volumeId']))
                self.log("+ created snapshot of volume ‘{0}’: ‘{1}’".format(v['volumeId'], snapshot.id))

                snapshot_tags = {}
                snapshot_tags.update(defn.tags)
                snapshot_tags.update(self.get_common_tags())
                snapshot_tags['Name'] = "{0} - {3} [{1} - {2}]".format(self.depl.description, self.name, device_stored, backup_id)

                self._retry(lambda: self._conn.create_tags([snapshot.id], snapshot_tags))
                backup[device_stored] = snapshot.id

        _backups[backup_id] = backup
        self.backups = _backups

    # devices - array of dictionaries, keys - /dev/nvme or /dev/xvd device name, values - device options
    def restore(self, defn, backup_id, devices=[]):
        self.stop()

        self.log("restoring machine ‘{0}’ to backup ‘{1}’".format(self.name, backup_id))
        for d in devices:
            self.log(" - {0}".format(d))

        for device_stored, v in self.sorted_block_device_mapping():
            device_real = device_name_stored_to_real(device_stored)

            if devices == [] or device_real in devices:
                # detach disks
                volume = nixops.ec2_utils.get_volume_by_id(self.connect(), v['volumeId'])
                if volume and volume.update() == "in-use":
                    self.log("detaching volume from ‘{0}’".format(self.name))
                    volume.detach()

                # attach backup disks
                snapshot_id = self.backups[backup_id][device_stored]
                self.log("creating volume from snapshot ‘{0}’".format(snapshot_id))

                self.wait_for_snapshot_to_become_completed(snapshot_id)

                new_volume = self._conn.create_volume(size=0, snapshot=snapshot_id, zone=self.zone)

                # Check if original volume is available, aka detached from the machine.
                if volume:
                    nixops.ec2_utils.wait_for_volume_available(self._conn, volume.id, self.logger)

                # Check if new volume is available.
                nixops.ec2_utils.wait_for_volume_available(self._conn, new_volume.id, self.logger)

                self.log("attaching volume ‘{0}’ to ‘{1}’ as {2}".format(new_volume.id, self.name, device_real))

                device_that_boto_expects = device_name_to_boto_expected(device_real) # boto expects only sd names
                new_volume.attach(self.vm_id, device_that_boto_expects)

                new_v = self.block_device_mapping[device_stored]

                if v.get('partOfImage', False) or v.get('charonDeleteOnTermination', False) or v.get('deleteOnTermination', False):
                    new_v['charonDeleteOnTermination'] = True
                    self._delete_volume(v['volumeId'], True)
                new_v['volumeId'] = new_volume.id
                self.update_block_device_mapping(device_stored, new_v)

    def wait_for_snapshot_to_become_completed(self, snapshot_id):
        def check_completed():
            res = self._get_snapshot_by_id(snapshot_id).status
            self.log_continue("[{0}] ".format(res))
            return res == 'completed'

        self.log_start("waiting for snapshot ‘{0}’ to have status ‘completed’... ".format(snapshot_id))
        nixops.util.check_wait(check_completed)
        self.log_end('')

    def create_after(self, resources, defn):
        # EC2 instances can require key pairs, IAM roles, security
        # groups, EBS volumes and elastic IPs.  FIXME: only depend on
        # the specific key pair / role needed for this instance.
        return {r for r in resources if
                isinstance(r, nixops.resources.ec2_keypair.EC2KeyPairState) or
                isinstance(r, nixops.resources.iam_role.IAMRoleState) or
                isinstance(r, nixops.resources.ec2_security_group.EC2SecurityGroupState) or
                isinstance(r, nixops.resources.ec2_placement_group.EC2PlacementGroupState) or
                isinstance(r, nixops.resources.ebs_volume.EBSVolumeState) or
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState) or
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState) or
                isinstance(r, nixops.resources.vpc_route.VPCRouteState) or
                isinstance(r, nixops.resources.elastic_file_system.ElasticFileSystemState) or
                isinstance(r, nixops.resources.elastic_file_system_mount_target.ElasticFileSystemMountTargetState)}

    def attach_volume(self, device_stored, volume_id):
        # type: (str, str) -> bool

        device_real = device_name_stored_to_real(device_stored)

        volume = nixops.ec2_utils.get_volume_by_id(self.session(), volume_id)
        if not volume:
            raise Exception("volume {0} doesn't exist, run check to update the state of the volume".format(volume_id))

        if volume.state == "in-use" and \
                self.vm_id != volume.attachments[0]['InstanceId'] and \
                self.depl.logger.confirm("volume ‘{0}’ is in use by instance ‘{1}’, "
                                         "are you sure you want to attach this volume?".format(volume_id, volume.attachments[0]['InstanceId'])):

            self.log_start("detaching volume ‘{0}’ from instance ‘{1}’... ".format(volume_id, volume.attachments[0]['InstanceId']))
            volume.detach_from_instance()

            def check_available():
                volume.reload()
                self.log_continue("[{0}] ".format(volume.state))
                return volume.state == 'available'

            nixops.util.check_wait(check_available)
            self.log_end('')

            volume.reload()
            if volume.state != "available":
                self.log("force detaching volume ‘{0}’ from instance ‘{1}’...".format(volume_id, volume.attachments[0]['InstanceId']))
                volume.detach_from_instance(Force=True)
                nixops.util.check_wait(check_available)

        self.log_start("attaching volume ‘{0}’ as ‘{1}’... ".format(volume_id, device_real))

        if self.vm_id != volume.volume.attachments[0]['InstanceId']:
            # Attach it.
            device_that_boto_expects = device_name_to_boto_expected(device_stored)
            volume.attach_to_instance(InstanceId=self.vm_id, Device=device_that_boto_expects)

        def check_attached():
            volume.reload()
            res = volume.state
            self.log_continue("[{0}] ".format(res or "not-attached"))
            return res == 'attached'

        # If volume is not in attached state, wait for it before going on.
        if volume.state != "attached":
            nixops.util.check_wait(check_attached)

        # Wait until the device is visible in the instance.
        def check_device():
            res = self.run_command("test -e {0}".format(device_real), check=False)
            return res == 0

        if not nixops.util.check_wait(check_device, initial=1, max_tries=10, exception=False):
            # If stopping times out, then do an unclean shutdown.
            self.log_end("(timed out)")

            self.log("can't find device ‘{0}’...".format(device_real))
            self.log('available devices:')
            self.run_command("lsblk")

            raise Exception("operation timed out")
        else:
            self.log_end('')

    def _assign_elastic_ip(self, elastic_ipv4, check):
        instance = self._get_instance()

        # Assign or release an elastic IP address, if given.
        if (self.elastic_ipv4 or "") != elastic_ipv4 or (instance.public_ip_address != elastic_ipv4) or check:
            if elastic_ipv4 != "":
                # wait until machine is in running state
                self.log_start("waiting for machine to be in running state... ".format(self.name))
                while True:
                    self.log_continue("[{0}] ".format(instance.state['Name']))
                    if instance.state['Name'] == "running":
                        break
                    if instance.state['Name'] not in {"running", "pending"}:
                        raise Exception(
                            "EC2 instance ‘{0}’ failed to reach running state (state is ‘{1}’)"
                            .format(self.vm_id, instance.state['Name']))
                    time.sleep(3)
                    instance = self._get_instance(update=True)
                self.log_end("")

                ec2 = self.session().client('ec2')
                addresses = ec2.describe_addresses(PublicIps=[elastic_ipv4])['Addresses']
                if addresses[0]['InstanceId'] != "" \
                    and addresses[0]['InstanceId'] is not None \
                    and addresses[0]['InstanceId'] != self.vm_id \
                    and not self.depl.logger.confirm(
                        "are you sure you want to associate IP address ‘{0}’, which is currently in use by instance ‘{1}’?".format(
                            elastic_ipv4, addresses[0]['InstanceId'])):
                    raise Exception("elastic IP ‘{0}’ already in use...".format(elastic_ipv4))
                else:
                    self.log("associating IP address ‘{0}’...".format(elastic_ipv4))
                    ec2.associate_address(AllocationId=addresses[0]['AllocationId'], InstanceId=self.vm_id)

                    self.log_start("waiting for address to be associated with this machine... ")
                    instance = self._get_instance(update=True)
                    while True:
                        self.log_continue("[{0}] ".format(instance.public_ip_address))
                        if instance.public_ip_address == elastic_ipv4:
                            break
                        time.sleep(3)
                        instance = self._get_instance(update=True)
                    self.log_end("")

                nixops.known_hosts.update(self.public_ipv4, elastic_ipv4, self.public_host_key)

                with self.depl._db:
                    self.elastic_ipv4 = elastic_ipv4
                    self.public_ipv4 = elastic_ipv4
                    self.ssh_pinged = False

            elif self.elastic_ipv4 is not None:
                ec2 = self.session().client('ec2')
                addresses = ec2.describe_addresses(PublicIps=[self.elastic_ipv4])['Addresses']

                if len(addresses) == 1 and addresses[0]['InstanceId'] == self.vm_id:
                    self.log("disassociating IP address ‘{0}’...".format(self.elastic_ipv4))
                    ec2.disassociate_address(PublicIp=self.elastic_ipv4)
                else:
                    self.log("address ‘{0}’ was not associated with instance ‘{1}’".format(self.elastic_ipv4, self.vm_id))

                with self.depl._db:
                    self.elastic_ipv4 = None
                    self.public_ipv4 = None
                    self.ssh_pinged = False

    def security_groups_to_ids(self, subnetId, groups):
        # type: (str, Iterable[str]) -> List[str]

        group_ids = [g for g in groups if g.startswith('sg-')]
        sg_names = [g for g in groups if not g.startswith('sg-')]
        if sg_names and subnetId:
            ec2 = self.session().resource('ec2')
            subnet = ec2.Subnet(subnetId)
            vpc_id = subnet.vpc_id
            group_ids += [nixops.ec2_utils.name_to_security_group(self.session(), g, vpc_id) for g in groups]

        return group_ids

    def _wait_for_spot_request_fulfillment(self, request_id):
        # type: (str) -> ...

        self.log_start("waiting for spot instance request ‘{0}’ to be fulfilled... ".format(self.spot_instance_request_id))
        while True:
            request = self._get_spot_instance_request_by_id(self.spot_instance_request_id)
            self.log_continue("[{0}] ".format(request.status.code))
            if request.status.code == "fulfilled":
                break

            if request.status.code in {"schedule-expired", "canceled-before-fulfillment", "bad-parameters", "system-error"}:
                self.spot_instance_request_id = None
                self.log_end("")
                raise Exception("spot instance request failed with result ‘{0}’".format(request.status.code))

            time.sleep(3)
        self.log_end("")

        instance = self._retry(lambda: self._get_instance(instance_id=request.instance_id))

        return instance

    def create_instance(self, defn, zone, user_data, ebs_optimized, args):
        # type: (EC2Definition, str, str, bool, Dict[str, Any]) -> ...
        IamInstanceProfile = {}  # type: Dict[str, str]
        if defn.instance_profile.startswith("arn:"):
            IamInstanceProfile["Arn"] = defn.instance_profile
        else:
            IamInstanceProfile["Name"] = defn.instance_profile

        if defn.subnet_id:
            if defn.security_groups and defn.security_groups != ["default"]:
                raise Exception("‘deployment.ec2.securityGroups’ is incompatible with ‘deployment.ec2.subnetId’")

            args['NetworkInterfaces'] = [dict(
                AssociatePublicIpAddress=defn.associate_public_ip_address,
                SubnetId=defn.subnet_id,
                DeviceIndex=0,
                Groups=self.security_groups_to_ids(defn.subnet_id, defn.security_group_ids)
            )]
        else:
            args['SecurityGroups'] = defn.security_groups

        if defn.spot_instance_price:
            args["InstanceMarketOptions"] = dict(
                MarketType="spot",
                SpotOptions=dict(
                    MaxPrice=str(defn.spot_instance_price/100.0),
                    SpotInstanceType=defn.spot_instance_request_type,
                    InstanceInterruptionBehavior=defn.spot_instance_interruption_behavior
                )
            )
            if defn.spot_instance_timeout:
                args["InstanceMarketOptions"]["SpotOptions"]["ValidUntil"] = (datetime.datetime.utcnow() +
                    datetime.timedelta(0, defn.spot_instance_timeout)).isoformat()

        placement = dict(
            AvailabilityZone=zone or ""
        )
        if defn.tenancy:
            placement['Tenancy'] = defn.tenancy

        args['InstanceType'] = defn.instance_type
        args['ImageId'] = defn.ami
        args['IamInstanceProfile'] = IamInstanceProfile
        args['KeyName'] = defn.key_pair
        args['Placement'] = placement
        args['UserData'] = user_data
        args['EbsOptimized'] = ebs_optimized
        args['MaxCount'] = 1  # We always want to deploy one instance.
        args['MinCount'] = 1

        # Use a client token to ensure that instance creation is
        # idempotent; i.e., if we get interrupted before recording
        # the instance ID, we'll get the same instance ID on the
        # next run.
        if not self.client_token:
            with self.depl._db:
                self.client_token = nixops.util.generate_random_string(length=48)  # = 64 ASCII chars
                self.state = self.STARTING

        args["ClientToken"] = self.client_token

        ec2 = self.session().client('ec2')

        reservation = self._retry(
            lambda: ec2.run_instances(**args)
        )

        if not defn.spot_instance_price:
            # On demand instance, no need to any more checks, return it.
            return self._get_instance(reservation["Instances"][0]["InstanceId"])

        with self.depl._db:
            self.spot_instance_price = defn.spot_instance_price
            self.spot_instance_request_id = reservation["Instances"][0]["SpotInstanceRequestId"]

        tags = {'Name': "{0} [{1}]".format(self.depl.description, self.name)}
        tags.update(defn.tags)
        tags.update(self.get_common_tags())
        self._retry(lambda: ec2.create_tags(Resources=[self.spot_instance_request_id], Tags=key_value_to_ec2_key_value(tags)))

        return self._wait_for_spot_request_fulfillment(self.spot_instance_request_id)

    def _cancel_spot_request(self):
        if self.spot_instance_request_id is None: return
        self.log_start("cancelling spot instance request ‘{0}’... ".format(self.spot_instance_request_id))

        # Cancel the request.
        request = self._get_spot_instance_request_by_id(self.spot_instance_request_id, allow_missing=True)
        if request is not None:
            request.cancel()

        # Wait until it's really cancelled. It's possible that the
        # request got fulfilled while we were cancelling it. In that
        # case, record the instance ID.
        while True:
            request = self._get_spot_instance_request_by_id(self.spot_instance_request_id, allow_missing=True)
            if request is None: break
            self.log_continue("[{0}] ".format(request.status.code))
            if request.instance_id is not None and request.instance_id != self.vm_id:
                if self.vm_id is not None:
                    raise Exception("spot instance request got fulfilled unexpectedly as instance ‘{0}’".format(request.instance_id))
                self.vm_id = request.instance_id
            if request.state != 'open': break
            time.sleep(3)

        self.log_end("")

        self.spot_instance_request_id = None


    def after_activation(self, defn):
        # Detach volumes that are no longer in the deployment spec.
        for device_stored, v in self.block_device_mapping.items():
            device_real = device_name_stored_to_real(device_stored)

            if device_stored not in defn.block_device_mapping and not v.get('partOfImage', False):
                if v.get('disk', '').startswith("ephemeral"):
                    raise Exception("cannot detach ephemeral device ‘{0}’ from EC2 instance ‘{1}’"
                    .format(device_real, self.name))

                assert v.get('volumeId', None)

                self.log("detaching device ‘{0}’...".format(device_real))
                volumes = self._conn.get_all_volumes([],
                    filters={'attachment.instance-id': self.vm_id, 'attachment.device': device_stored, 'volume-id': v['volumeId']})
                assert len(volumes) <= 1

                if len(volumes) == 1:
                    if v.get('encrypt', False) and v.get('encryptionType', "luks") == "luks":
                        device_real_mapper = device_real.replace("/dev/", "/dev/mapper/")
                        self.run_command("umount -l {0}".format(device_real_mapper), check=False)
                        self.run_command("cryptsetup luksClose {0}".format(device_real.replace("/dev/", "")), check=False)
                    else:
                        self.run_command("umount -l {0}".format(device_real), check=False)
                    if not self._conn.detach_volume(volumes[0].id, instance_id=self.vm_id, device=device_stored):
                        raise Exception("unable to detach volume ‘{0}’ from EC2 machine ‘{1}’".format(v['volumeId'], self.name))
                        # FIXME: Wait until the volume is actually detached.

                if v.get('charonDeleteOnTermination', False) or v.get('deleteOnTermination', False):
                    self._delete_volume(v['volumeId'])

                self.update_block_device_mapping(device_stored, None)

    def create(self, defn, check, allow_reboot, allow_recreate):
        # type: (EC2Definition, bool, bool, bool) -> None
        assert isinstance(defn, EC2Definition)

        if self.state != self.UP:
            check = True

        self.set_common_state(defn)

        if defn.subnet_id.startswith("res-"):
            res = self.depl.get_typed_resource(defn.subnet_id[4:].split(".")[0], "vpc-subnet")
            defn.subnet_id = res._state['subnetId']

        # Figure out the access key.
        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
        
        self.private_key_file = defn.private_key or None

        if self.region is None:
            self.region = defn.region
        elif self.region != defn.region:
            self.warn("cannot change region of a running instance (from ‘{}‘ to ‘{}‘)".format(self.region, defn.region))

        if self.profile is None:
            self.profile = defn.profile

        if self.key_pair and self.key_pair != defn.key_pair:
            raise Exception("cannot change key pair of an existing instance (from ‘{}‘ to ‘{}‘)".format(self.key_pair, defn.key_pair))

        # Stop the instance (if allowed) to change instance attributes
        # such as the type.
        if self.vm_id and allow_reboot and self._booted_from_ebs() and (self.instance_type != defn.instance_type or self.ebs_optimized != defn.ebs_optimized):
            self.stop()
            check = True

        # Check whether the instance hasn't been killed behind our
        # backs.  Restart stopped instances.
        if self.vm_id and check:
            instance = self._get_instance(allow_missing=True)

            if instance is None or instance.state['Name'] in {"shutting-down", "terminated"}:
                if not allow_recreate:
                    raise Exception("EC2 instance ‘{0}’ went away; use ‘--allow-recreate’ to create a new one".format(self.name))
                self.log("EC2 instance went away (state ‘{0}’), will recreate".format(instance.state['Name'] if instance else "gone"))
                self._reset_state()
                self.region = defn.region
            elif instance.state['Name'] == "stopped":
                self.log("EC2 instance was stopped, restarting...")

                # Modify the instance type, if desired.
                if self.instance_type != defn.instance_type:
                    self.log("changing instance type from ‘{0}’ to ‘{1}’...".format(self.instance_type, defn.instance_type))
                    instance.modify_attribute(InstanceType={'Value': defn.instance_type})
                    self.instance_type = defn.instance_type

                if self.ebs_optimized != defn.ebs_optimized:
                    self.log("changing ebs optimized flag from ‘{0}’ to ‘{1}’...".format(self.ebs_optimized, defn.ebs_optimized))
                    instance.modify_attribute(EbsOptimized={'Value': defn.ebs_optimized})
                    self.ebs_optimized = defn.ebs_optimized

                # When we restart, we'll probably get a new IP.  So forget the current one.
                self.public_ipv4 = None
                self.private_ipv4 = None

                instance.start()

                self.state = self.STARTING

        resize_root = False
        update_instance_profile = True

        # Create the instance.
        if not self.vm_id:

            self.log("creating EC2 instance (AMI ‘{0}’, type ‘{1}’, region ‘{2}’)...".format(
                defn.ami, defn.instance_type, self.region))
            if not self.client_token and not self.spot_instance_request_id:
                self._reset_state()
                self.region = defn.region

            ec2 = self.session().resource('ec2')
            ami = ec2.Image(defn.ami)
            self.root_device_type = ami.root_device_type

            # Check if we need to resize the root disk
            resize_root = defn.root_disk_size != 0 and ami.root_device_type == 'ebs'

            args = dict()

            # Set the initial block device mapping to the ephemeral
            # devices defined in the spec.  These cannot be changed
            # later.
            args['BlockDeviceMappings'] = []

            for device_stored, v in defn.block_device_mapping.iteritems():
                device_real = device_name_stored_to_real(device_stored)
                # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/device_naming.html
                ebs_disk = not v['disk'].startswith("ephemeral")

                # though /dev/nvme0 is to not recommended, it's not possible that it will appear here, because /dev/nvme0 is always attached as root
                device_name_not_recommended_for_ebs_disks = re.match("/dev/xvd[a-e]", device_real)

                if ebs_disk and device_name_not_recommended_for_ebs_disks:
                    raise Exception("non-ephemeral disk not allowed on device ‘{0}’; use /dev/xvdf or higher".format(device_real))

                if v['disk'].startswith("ephemeral"):
                    ephemeral_mapping = dict(
                        DeviceName=device_name_to_boto_expected(device_real),
                        VirtualName=v['disk']
                    )
                    args['BlockDeviceMappings'].append(ephemeral_mapping)
                    self.update_block_device_mapping(device_stored, v)

            root_device = ami.root_device_name
            if resize_root:
                root_mapping = dict(
                    DeviceName=root_device,
                    Ebs=dict(
                        DeleteOnTermination=True,
                        VolumeSize=defn.root_disk_size,
                        VolumeType=ami.block_device_mappings[0]['Ebs']['VolumeType']
                    )
                )
                args['BlockDeviceMappings'].append(root_mapping)
            # If we're attaching any EBS volumes, then make sure that
            # we create the instance in the right placement zone.
            zone = defn.zone or None
            for device_stored, v in defn.block_device_mapping.iteritems():
                if not v['disk'].startswith("vol-"): continue
                # Make note of the placement zone of the volume.
                volume = nixops.ec2_utils.get_volume_by_id(self.session(), v['disk'])
                if not zone:
                    self.log("starting EC2 instance in zone ‘{0}’ due to volume ‘{1}’".format(
                            volume.availability_zone, v['disk']))
                    zone = volume.availability_zone
                elif zone != volume.availability_zone:
                    raise Exception("unable to start EC2 instance ‘{0}’ in zone ‘{1}’ because volume ‘{2}’ is in zone ‘{3}’"
                                    .format(self.name, zone, v['disk'], volume.availability_zone))

            # Do we want an EBS-optimized instance?
            prefer_ebs_optimized = False
            for device_stored, v in defn.block_device_mapping.iteritems():
                if v['volumeType'] != "standard":
                    prefer_ebs_optimized = True

            # if we have PIOPS volume and instance type supports EBS Optimized flags, then use ebs_optimized
            ebs_optimized = prefer_ebs_optimized and defn.ebs_optimized
            # Generate a public/private host key.
            if not self.public_host_key:
                private, public = nixops.util.create_key_pair(type=defn.host_key_type())
                with self.depl._db:
                    self.public_host_key = public
                    self.private_host_key = private

            user_data = "SSH_HOST_{2}_KEY_PUB:{0}\nSSH_HOST_{2}_KEY:{1}\n".format(
                self.public_host_key, self.private_host_key.replace("\n", "|"),
                defn.host_key_type().upper())

            instance = self.create_instance(defn, zone, user_data, ebs_optimized, args)
            update_instance_profile = False

            with self.depl._db:
                self.vm_id = instance.id
                self.ami = defn.ami
                self.instance_type = defn.instance_type
                self.ebs_optimized = ebs_optimized
                self.key_pair = defn.key_pair
                self.security_groups = defn.security_groups
                self.placement_group = defn.placement_group
                self.zone = instance.placement['AvailabilityZone']
                self.tenancy = defn.tenancy
                self.instance_profile = defn.instance_profile
                self.client_token = None
                self.private_host_key = None

            # Cancel spot instance request, it isn't needed after the
            # instance has been provisioned in case of "one-time" requests
            if defn.spot_instance_request_type == "one-time":
                self._cancel_spot_request()


        # There is a short time window during which EC2 doesn't
        # know the instance ID yet.  So wait until it does.
        if self.state != self.UP or check:
            while True:
                if self._get_instance(allow_missing=True): break
                self.log("EC2 instance ‘{0}’ not known yet, waiting...".format(self.vm_id))
                time.sleep(3)

        if not self.virtualization_type:
            self.virtualization_type = self._get_instance().virtualization_type

        instance = self._get_instance()

        # Warn about some EC2 options that we cannot update for an existing instance.
        if self.instance_type != defn.instance_type:
            self.warn("cannot change type of a running instance (from ‘{0}‘ to ‘{1}‘): use ‘--allow-reboot’".format(self.instance_type, defn.instance_type))
        if self.ebs_optimized and self.ebs_optimized != defn.ebs_optimized:
            self.warn("cannot change ebs optimized attribute of a running instance: use ‘--allow-reboot’")
        if defn.zone and self.zone != defn.zone:
            self.warn("cannot change availability zone of a running (from ‘{0}‘ to ‘{1}‘)".format(self.zone, defn.zone))
        if not defn.subnet_id and not instance.subnet_id and set(defn.security_groups) != set(self.security_groups):
            self.warn(
                'cannot change security groups of an existing instance (from [{0}] to [{1}])'.format(
                    ", ".join(set(self.security_groups)),
                    ", ".join(set(defn.security_groups)))
            )

        instance_groups = [g['GroupId'] for g in instance.security_groups]
        if defn.subnet_id:
            new_instance_groups = self.security_groups_to_ids(defn.subnet_id, defn.security_group_ids)
        elif instance.vpc_id:
            new_instance_groups = self.security_groups_to_ids(instance.subnet_id, defn.security_groups)

        if instance.vpc_id and set(instance_groups) != set(new_instance_groups):
            self.log("updating security groups from {0} to {1}...".format(instance_groups, new_instance_groups))
            ni = instance.network_interfaces[0]
            ni.modify_attribute(Groups=new_instance_groups)

        if defn.placement_group != (self.placement_group or ""):
            self.warn(
                'cannot change placement group of an existing instance (from ‘{0}’ to ‘{1}’)'.format(
                    self.placement_group or "",
                    defn.placement_group)
            )

        # update iam instance profiles of instance
        if update_instance_profile and (self.instance_profile != defn.instance_profile or check):
            ec2 = self.session().client('ec2')
            assocs = self._retry(lambda: ec2.describe_iam_instance_profile_associations(Filters=[{'Name': 'instance-id', 'Values': [self.vm_id]}])['IamInstanceProfileAssociations'])
            if len(assocs) > 0 and self.instance_profile != assocs[0]['IamInstanceProfile']['Arn']:
                self.log("disassociating instance profile {}".format(assocs[0]['IamInstanceProfile']['Arn']))
                ec2.disassociate_iam_instance_profile(AssociationId=assocs[0]['AssociationId'])
                nixops.util.check_wait(lambda: len(self._retry(lambda: ec2.describe_iam_instance_profile_associations(Filters=[{'Name': 'instance-id', 'Values': [self.vm_id]}])['IamInstanceProfileAssociations'])) == 0)

            if defn.instance_profile != "":
                if defn.instance_profile.startswith('arn:'):
                    iip = {'Arn': defn.instance_profile}
                else:
                    iip = {'Name': defn.instance_profile}
                self.log("associating instance profile {}".format(defn.instance_profile))
                self._retry(lambda: ec2.associate_iam_instance_profile(IamInstanceProfile=iip, InstanceId=self.vm_id))

            with self.depl._db:
                self.instance_profile = defn.instance_profile

        # Reapply tags if they have changed.
        common_tags = defn.tags
        if defn.owners:
            common_tags['Owners'] = ", ".join(defn.owners)
        self.update_tags(self.session(), self.vm_id, user_tags=common_tags, check=check)

        # Reapply sourceDestCheck if it has changed.
        if self.source_dest_check != defn.source_dest_check:
            instance.modify_attribute("sourceDestCheck", defn.source_dest_check)
            self.source_dest_check = defn.source_dest_check

        # Assign the elastic IP.  If necessary, dereference the resource.
        elastic_ipv4 = defn.elastic_ipv4
        if elastic_ipv4.startswith("res-"):
            res = self.depl.get_typed_resource(elastic_ipv4[4:], "elastic-ip")
            elastic_ipv4 = res.public_ipv4
        self._assign_elastic_ip(elastic_ipv4, check)

        with self.depl._db:
            self.use_private_ip_address = defn.use_private_ip_address
            self.associate_public_ip_address = defn.associate_public_ip_address

        # Wait for the IP address.
        if (self.associate_public_ip_address and not self.public_ipv4) \
           or \
           (self.use_private_ip_address and not self.private_ipv4) \
           or \
           check:
            self._wait_for_ip()

        if defn.dns_hostname:
            self._update_route53(defn)

        # Wait until the instance is reachable via SSH.
        self.wait_for_ssh(check=check)

        # Generate a new host key on the instance and restart
        # sshd. This is necessary because we can't count on the
        # instance data to remain secret.  FIXME: not atomic.
        if "NixOps auto-generated key" in self.public_host_key:
            self.log("replacing temporary host key...")
            key_type = defn.host_key_type()
            new_key = self.run_command(
                "rm -f /etc/ssh/ssh_host_{0}_key*; systemctl restart sshd; cat /etc/ssh/ssh_host_{0}_key.pub"
                .format(key_type),
                capture_stdout=True).rstrip()
            self.public_host_key = new_key
            nixops.known_hosts.update(None, self._ip_for_ssh_key(), self.public_host_key)

        # Add disks that were in the original device mapping of image.
        if self.first_boot:
            for device in self._get_instance().block_device_mappings:
                if device['DeviceName'] not in self.block_device_mapping and device['Ebs']['VolumeId']:
                    bdm = {'volumeId': device['Ebs']['VolumeId'], 'partOfImage': True}
                    self.update_block_device_mapping(device['DeviceName'], bdm) # TODO: it stores root device as sd though its really attached as nvme
            self.first_boot = False

        # Detect if volumes were manually detached.  If so, reattach
        # them.
        devices = [device['DeviceName'] for device in self._get_instance().block_device_mappings]
        for device_stored, v in self.block_device_mapping.items():
            if device_name_to_boto_expected(device_stored) not in devices and not v.get('needsAttach', False) and v.get('volumeId', None):
                device_real = device_name_stored_to_real(device_stored)
                self.warn("device ‘{0}’ was manually detached!".format(device_real))
                v['needsAttach'] = True
                self.update_block_device_mapping(device_stored, v)

        # Detect if volumes were manually destroyed.
        for device_stored, v in self.block_device_mapping.items():
            if v.get('needsAttach', False):
                volume = nixops.ec2_utils.get_volume_by_id(self.session(), v['volumeId'], allow_missing=True)
                if volume:
                    continue
                if device_stored not in defn.block_device_mapping:
                    self.warn("forgetting about volume ‘{0}’ that no longer exists and is no longer needed by the deployment specification".format(v['volumeId']))
                else:
                    if not allow_recreate:
                        raise Exception("volume ‘{0}’ (used by EC2 instance ‘{1}’) no longer exists; "
                                        "run ‘nixops stop’, then ‘nixops deploy --allow-recreate’ to create a new, empty volume"
                                        .format(v['volumeId'], self.name))
                    self.warn("volume ‘{0}’ has disappeared; will create an empty volume to replace it".format(v['volumeId']))
                self.update_block_device_mapping(device_stored, None)

        # Create missing volumes.
        ec2 = self.session().client('ec2')
        for device_stored, v in defn.block_device_mapping.iteritems():
            device_real = device_name_stored_to_real(device_stored)

            volume = None
            if v['disk'] == '':
                if device_stored in self.block_device_mapping:
                    continue
                self.log("creating EBS volume of {0} GiB...".format(v['size']))
                ebs_encrypt = v.get('encryptionType', "luks") == "ebs"
                volume = ec2.create_volume(Size=v['size'], AvailabilityZone=self.zone, VolumeType=v['volumeType'], Iops=v['iops'], Encrypted=ebs_encrypt)
                v['volumeId'] = volume['VolumeId']

            elif v['disk'].startswith("vol-"):
                if device_stored in self.block_device_mapping:
                    cur_volume_id = self.block_device_mapping[device_stored]['volumeId']
                    if cur_volume_id != v['disk']:
                        raise Exception("cannot attach EBS volume ‘{0}’ to ‘{1}’ because volume ‘{2}’ is already attached there".format(v['disk'], device_real, cur_volume_id))
                    continue
                v['volumeId'] = v['disk']

            elif v['disk'].startswith("res-"):
                res_name = v['disk'][4:]
                res = self.depl.get_typed_resource(res_name, "ebs-volume")
                if res.state != self.UP:
                    raise Exception("EBS volume ‘{0}’ has not been created yet".format(res_name))
                assert res.volume_id
                if device_stored in self.block_device_mapping:
                    cur_volume_id = self.block_device_mapping[device_stored]['volumeId']
                    if cur_volume_id != res.volume_id:
                        raise Exception("cannot attach EBS volume ‘{0}’ to ‘{1}’ because volume ‘{2}’ is already attached there".format(res_name, device_real, cur_volume_id))
                    continue
                v['volumeId'] = res.volume_id

            elif v['disk'].startswith("snap-"):
                if device_stored in self.block_device_mapping:
                    continue
                self.log("creating volume from snapshot ‘{0}’...".format(v['disk']))
                volume = ec2.create_volume(Size=v['size'], SnapshotId=v['disk'], AvailabilityZone=self.zone, VolumeType=v['volumeType'], Iops=v['iops'])
                v['volumeId'] = volume['VolumeId']

            else:
                if device_stored in self.block_device_mapping:
                    v['needsAttach'] = False
                    self.update_block_device_mapping(device_stored, v)
                    continue
                raise Exception("adding device mapping ‘{0}’ to a running instance is not (yet) supported".format(v['disk']))

            # ‘charonDeleteOnTermination’ denotes whether we have to
            # delete the volume.  This is distinct from
            # ‘deleteOnTermination’ for backwards compatibility with
            # the time that we still used auto-created volumes.
            v['charonDeleteOnTermination'] = v['deleteOnTermination']
            v['needsAttach'] = True
            self.update_block_device_mapping(device_stored, v)

            # Wait for volume to get to available state for newly
            # created volumes only (EC2 sometimes returns weird
            # temporary states for newly created volumes, e.g. shortly
            # in-use).  Doing this after updating the device mapping
            # state, to make it recoverable in case an exception
            # happens (e.g. in other machine's deployments).
            if volume:
                nixops.ec2_utils.wait_for_volume_available(self.session(), volume.id, self.logger)

        # Always apply tags to the volumes we just created.
        ec2 = self.session().client('ec2')
        for device_stored, v in self.block_device_mapping.items():
            device_real = device_name_stored_to_real(device_stored)

            if not (('disk' in v and not (v['disk'].startswith("ephemeral")
                                          or v['disk'].startswith("res-")
                                          or v['disk'].startswith("vol-")))
                    or 'partOfImage' in v):
                continue
            volume_tags = {}
            volume_tags.update(common_tags)
            volume_tags.update(defn.tags)
            volume_tags['Name'] = "{0} [{1} - {2}]".format(self.depl.description, self.name, device_real)

            self._retry(lambda: ec2.create_tags(Resources=[v['volumeId']], Tags=key_value_to_ec2_key_value(volume_tags)))

        # Attach missing volumes.
        for device_stored, v in self.sorted_block_device_mapping():
            if v.get('needsAttach', False):
                self.attach_volume(device_stored, v['volumeId'])
                del v['needsAttach']
                self.update_block_device_mapping(device_stored, v)

        # FIXME: process changes to the deleteOnTermination flag.

        # Auto-generate LUKS keys if the model didn't specify one.
        for device_stored, v in self.block_device_mapping.items():
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") == "" and v.get('encryptionType', "luks") == "luks":
                v['generatedKey'] = nixops.util.generate_random_string(length=256)
                self.update_block_device_mapping(device_stored, v)

    def _retry_route53(self, f, error_codes=[]):
        return nixops.ec2_utils.retry(f, error_codes = ['Throttling', 'PriorRequestNotComplete']+error_codes, logger=self)

    def _update_route53(self, defn):
        import boto.route53
        import boto.route53.record

        self.dns_hostname = defn.dns_hostname.lower()
        self.dns_ttl = defn.dns_ttl
        self.route53_access_key_id = defn.route53_access_key_id or nixops.ec2_utils.get_access_key_id()
        self.route53_use_public_dns_name = defn.route53_use_public_dns_name
        self.route53_private = defn.route53_private

        if self.route53_private:
            if self.route53_use_public_dns_name:
                raise Exception("Can not add record for ‘{0}’, because private CNAME records are not implemented in NixOps. You may choose to use an ‘A’ record instead by setting ‘usePublicDNSName = false’.".format(self.dns_hostname))

            record_type = 'A'
            dns_value = self.private_ipv4

        else:
            if not self.public_ipv4:
                raise Exception("No public ipv4 address has been associated with ‘{0}’. If this record is intended for a public cloud host, make sure it is defined and its public IP address is known to NixOps. If this is record is intended for a private cloud, use ‘private = true’ to use the private IP adress instead.".format(self.dns_hostname))

            record_type = 'CNAME' if self.route53_use_public_dns_name else 'A'
            dns_value = self.public_dns_name if self.route53_use_public_dns_name else self.public_ipv4

        self.log('sending Route53 DNS: {0} {1} {2}'.format(self.dns_hostname, record_type, dns_value))

        self.connect_route53()

        hosted_zone = ".".join(self.dns_hostname.split(".")[1:])
        zones = self._retry_route53(lambda: self._conn_route53.get_all_hosted_zones())

        def testzone(hosted_zone, zone):
            """returns True if there is a subcomponent match"""
            hostparts = hosted_zone.split(".")
            zoneparts = zone.Name.split(".")[:-1] # strip the last ""

            return hostparts[::-1][:len(zoneparts)][::-1] == zoneparts

        zones = [zone for zone in zones['ListHostedZonesResponse']['HostedZones'] if testzone(hosted_zone, zone)]
        if len(zones) == 0:
            raise Exception('hosted zone for {0} not found'.format(hosted_zone))

        # use hosted zone with longest match
        zones = sorted(zones, key=lambda x: len(x.Name), reverse=True)
        zoneid = zones[0]['Id'].split("/")[2]
        dns_name = '{0}.'.format(self.dns_hostname)

        prev_a_rrs = [prev for prev
                      in self._retry_route53(lambda: self._conn_route53.get_all_rrsets(
                          hosted_zone_id=zoneid,
                          type="A",
                          name=dns_name
                      ))
                      if prev.name == dns_name
                      and prev.type == "A"]

        prev_cname_rrs = [prev for prev
                          in self._retry_route53(lambda: self._conn_route53.get_all_rrsets(
                              hosted_zone_id=zoneid,
                              type="CNAME",
                              name=self.dns_hostname
                          ))
                          if prev.name == dns_name
                          and prev.type == "CNAME"]

        changes = boto.route53.record.ResourceRecordSets(connection=self._conn_route53, hosted_zone_id=zoneid)
        if len(prev_a_rrs) > 0:
            for prevrr in prev_a_rrs:
                change = changes.add_change("DELETE", self.dns_hostname, "A", ttl=prevrr.ttl)
                change.add_value(",".join(prevrr.resource_records))
        if len(prev_cname_rrs) > 0:
            for prevrr in prev_cname_rrs:
                change = changes.add_change("DELETE", prevrr.name, "CNAME", ttl=prevrr.ttl)
                change.add_value(",".join(prevrr.resource_records))

        change = changes.add_change("CREATE", self.dns_hostname, record_type, ttl=self.dns_ttl)
        change.add_value(dns_value)
        # add InvalidChangeBatch to error codes to retry on. Unfortunately AWS sometimes returns
        # this due to eventual consistency
        self._retry_route53(lambda: changes.commit(), error_codes=['InvalidChangeBatch'])


    def _delete_volume(self, volume_id, allow_keep=False):
        if not self.depl.logger.confirm("are you sure you want to destroy EBS volume ‘{0}’?".format(volume_id)):
            if allow_keep:
                return
            else:
                raise Exception("not destroying EBS volume ‘{0}’".format(volume_id))
        self.log("destroying EBS volume ‘{0}’...".format(volume_id))
        volume = nixops.ec2_utils.get_volume_by_id(self.connect(), volume_id, allow_missing=True)
        if not volume: return
        nixops.util.check_wait(lambda: volume.update() == 'available')
        volume.delete()


    def destroy(self, wipe=False):
        self._cancel_spot_request()

        if not (self.vm_id or self.client_token):
            return True

        if not self.depl.logger.confirm("are you sure you want to destroy EC2 machine ‘{0}’?".format(self.name)):
            return False

        if wipe:
            log.warn("wipe is not supported")

        self.log_start("destroying EC2 machine... ".format(self.name))

        # Find the instance, either by its ID or by its client token.
        # The latter allows us to destroy instances that were "leaked"
        # in create() due to it being interrupted after the instance
        # was created but before it registered the ID in the database.
        instance = None
        if self.vm_id:
            instance = self._get_instance(allow_missing=True)
        else:
            ec2c = self.session().client('ec2')
            ec2r = self.session().resource('ec2')
            reservations = ec2c.describe_instances(Filters=[{'Name': 'client-token', 'Values': [self.client_token]}])['Reservations']
            if len(reservations) > 0:
                self.vm_id = reservations[0]['Instances'][0]['InstanceId']
                instance = ec2r.Instance(self.vm_id)

        if instance:
            instance.terminate()

            # Wait until it's really terminated.
            while True:
                self.log_continue("[{0}] ".format(instance.state['Name']))
                if instance.state['Name'] == "terminated":
                    break
                time.sleep(3)
                instance = self._get_instance(update=True)

        self.log_end("")

        nixops.known_hosts.update(self.public_ipv4, None, self.public_host_key)

        # Destroy volumes created for this instance.
        for device_stored, v in self.block_device_mapping.items():
            if v.get('charonDeleteOnTermination', False):
                self._delete_volume(v['volumeId'], True)
                self.update_block_device_mapping(device_stored, None)

        return True

    def stop(self):
        # type: () -> None

        if not self._booted_from_ebs():
            self.warn("cannot stop non-EBS-backed instance")
            return

        if not self.depl.logger.confirm("are you sure you want to stop machine '{}'".format(self.name)):
            return

        self.log_start("stopping EC2 machine... ")

        instance = self._get_instance()
        instance.stop()  # no-op if the machine is already stopped

        self.state = self.STOPPING

        # Wait until it's really stopped.
        def check_stopped():
            # type: () -> bool
            instance = self._get_instance(update=True)
            self.log_continue("[{0}] ".format(instance.state))
            if instance.state['Name'] == "stopped":
                return True
            if instance.state['Name'] not in {"running", "stopping"}:
                raise Exception(
                    "EC2 instance ‘{0}’ failed to stop (state is ‘{1}’)"
                    .format(self.vm_id, instance.state))
            return False

        if not nixops.util.check_wait(check_stopped, initial=3, max_tries=300, exception=False):  # = 15 min
            # If stopping times out, then do an unclean shutdown.
            self.log_end("(timed out)")
            self.log_start("force-stopping EC2 machine... ")
            instance.stop(Force=True)
            if not nixops.util.check_wait(check_stopped, initial=3, max_tries=100, exception=False):  # = 5 min
                # Amazon docs suggest doing a force stop twice...
                self.log_end("(timed out)")
                self.log_start("force-stopping EC2 machine... ")
                instance.stop(Force=True)
                nixops.util.check_wait(check_stopped, initial=3, max_tries=100)  # = 5 min

        self.log_end("")

        self.state = self.STOPPED
        self.ssh_master = None


    def start(self):
        if not self._booted_from_ebs():
            return

        self.log("starting EC2 machine...")

        instance = self._get_instance()
        instance.start()  # no-op if the machine is already started

        self.state = self.STARTING

        # Wait until it's really started, and obtain its new IP
        # address.  Warn the user if the IP address has changed (which
        # is generally the case).
        prev_private_ipv4 = self.private_ipv4
        prev_public_ipv4 = self.public_ipv4

        if self.elastic_ipv4:
            self.log("restoring previously attached elastic IP")
            self._assign_elastic_ip(self.elastic_ipv4, True)

        self._wait_for_ip()

        if prev_private_ipv4 != self.private_ipv4 or prev_public_ipv4 != self.public_ipv4:
            self.warn("IP address has changed, you may need to run ‘nixops deploy’")

        self.wait_for_ssh(check=True)
        self.send_keys()

    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        self.connect()
        instance = self._get_instance(allow_missing=True)
        old_state = self.state
        #self.log("instance state is ‘{0}’".format(instance.state if instance else "gone"))

        if instance is None or instance.state in {"shutting-down", "terminated"}:
            self.state = self.MISSING
            self.vm_id = None
            return

        res.exists = True
        if instance.state == "pending":
            res.is_up = False
            self.state = self.STARTING

        elif instance.state == "running":
            res.is_up = True

            res.disks_ok = True
            for device_stored, v in self.block_device_mapping.items():
                device_real = device_name_stored_to_real(device_stored)
                device_that_boto_expects = device_name_to_boto_expected(device_real) # boto expects only sd names

                if device_that_boto_expects not in instance.block_device_mapping.keys() and v.get('volumeId', None):
                    res.disks_ok = False
                    res.messages.append("volume ‘{0}’ not attached to ‘{1}’".format(v['volumeId'], device_real))
                    volume = nixops.ec2_utils.get_volume_by_id(self.connect(), v['volumeId'], allow_missing=True)
                    if not volume:
                        res.messages.append("volume ‘{0}’ no longer exists".format(v['volumeId']))

                if device_that_boto_expects in instance.block_device_mapping.keys() and instance.block_device_mapping[device_that_boto_expects].status != 'attached' :
                    res.disks_ok = False
                    res.messages.append("volume ‘{0}’ on device ‘{1}’ has unexpected state: ‘{2}’".format(v['volumeId'], device_real, instance.block_device_mapping[device_stored].status))


            if self.private_ipv4 != instance.private_ip_address or self.public_ipv4 != instance.ip_address:
                self.warn("IP address has changed, you may need to run ‘nixops deploy’")
                self.private_ipv4 = instance.private_ip_address
                self.public_ipv4 = instance.ip_address

            MachineState._check(self, res)

        elif instance.state == "stopping":
            res.is_up = False
            self.state = self.STOPPING

        elif instance.state == "stopped":
            res.is_up = False
            self.state = self.STOPPED

        # check for scheduled events
        instance_status = self._conn.get_all_instance_status(instance_ids=[instance.id])
        for ist in instance_status:
            if ist.events:
                for e in ist.events:
                    res.messages.append("Event ‘{0}’:".format(e.code))
                    res.messages.append("  * {0}".format(e.description))
                    res.messages.append("  * {0} - {1}".format(e.not_before, e.not_after))


    def reboot(self, hard=False):
        self.log("rebooting EC2 machine...")
        instance = self._get_instance()
        instance.reboot()
        self.state = self.STARTING


    def get_console_output(self):
        if not self.vm_id:
            raise Exception("cannot get console output of non-existant machine ‘{0}’".format(self.name))
        self.connect()
        return self._conn.get_console_output(self.vm_id).output or "(not available)"


    def next_charge_time(self):
        if not self.start_time:
            return None
        # EC2 instances are paid for by the hour.
        uptime = time.time() - self.start_time
        return self.start_time + int(math.ceil(uptime / 3600.0) * 3600.0)

    def sorted_block_device_mapping(self):
        """In order to preserve nvme devices names volumes should be attached in lexicographic order (ordered by device name)."""
        return sorted(self.block_device_mapping.items())