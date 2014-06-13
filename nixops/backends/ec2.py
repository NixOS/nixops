# -*- coding: utf-8 -*-

import os
import os.path
import sys
import re
import time
import socket
import getpass
import shutil
import boto.ec2
import boto.ec2.blockdevicemapping
from nixops.backends import MachineDefinition, MachineState
from nixops.nix_expr import Function, RawValue
from nixops.resources.ebs_volume import EBSVolumeState
from nixops.resources.elastic_ip import ElasticIPState
import nixops.util
import nixops.ec2_utils
import nixops.known_hosts
from xml import etree

class EC2InstanceDisappeared(Exception):
    pass

class EC2Definition(MachineDefinition):
    """Definition of an EC2 machine."""

    @classmethod
    def get_type(cls):
        return "ec2"

    def __init__(self, xml):
        MachineDefinition.__init__(self, xml)
        x = xml.find("attrs/attr[@name='ec2']/attrs")
        assert x is not None
        self.access_key_id = x.find("attr[@name='accessKeyId']/string").get("value")
        self.type = x.find("attr[@name='type']/string").get("value")
        self.region = x.find("attr[@name='region']/string").get("value")
        self.zone = x.find("attr[@name='zone']/string").get("value")
        self.controller = x.find("attr[@name='controller']/string").get("value")
        self.ami = x.find("attr[@name='ami']/string").get("value")
        if self.ami == "":
            raise Exception("no AMI defined for EC2 machine ‘{0}’".format(self.name))
        self.instance_type = x.find("attr[@name='instanceType']/string").get("value")
        self.key_pair = x.find("attr[@name='keyPair']/string").get("value")
        self.private_key = x.find("attr[@name='privateKey']/string").get("value")
        self.security_groups = [e.get("value") for e in x.findall("attr[@name='securityGroups']/list/string")]
        self.instance_profile = x.find("attr[@name='instanceProfile']/string").get("value")
        self.tags = {k.get("name"): k.find("string").get("value") for k in x.findall("attr[@name='tags']/attrs/attr")}
        self.root_disk_size = int(x.find("attr[@name='ebsInitialRootDiskSize']/int").get("value"))
        self.spot_instance_price = int(x.find("attr[@name='spotInstancePrice']/int").get("value"))
        self.ebs_optimized = x.find("attr[@name='ebsOptimized']/bool").get("value") == "true"

        def f(xml):
            return {'disk': xml.find("attrs/attr[@name='disk']/string").get("value"),
                    'size': int(xml.find("attrs/attr[@name='size']/int").get("value")),
                    'iops': int(xml.find("attrs/attr[@name='iops']/int").get("value")),
                    'fsType': xml.find("attrs/attr[@name='fsType']/string").get("value"),
                    'deleteOnTermination': xml.find("attrs/attr[@name='deleteOnTermination']/bool").get("value") == "true",
                    'encrypt': xml.find("attrs/attr[@name='encrypt']/bool").get("value") == "true",
                    'passphrase': xml.find("attrs/attr[@name='passphrase']/string").get("value")}

        self.block_device_mapping = {_xvd_to_sd(k.get("name")): f(k) for k in x.findall("attr[@name='blockDeviceMapping']/attrs/attr")}
        self.elastic_ipv4 = x.find("attr[@name='elasticIPv4']/string").get("value")

        x = xml.find("attrs/attr[@name='route53']/attrs")
        assert x is not None
        self.dns_hostname = x.find("attr[@name='hostName']/string").get("value")
        self.dns_ttl = x.find("attr[@name='ttl']/int").get("value")
        self.route53_access_key_id = x.find("attr[@name='accessKeyId']/string").get("value")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region or self.zone or "???")


class EC2State(MachineState):
    """State of an EC2 machine."""

    @classmethod
    def get_type(cls):
        return "ec2"

    state = nixops.util.attr_property("state", MachineState.MISSING, int)  # override
    public_ipv4 = nixops.util.attr_property("publicIpv4", None)
    private_ipv4 = nixops.util.attr_property("privateIpv4", None)
    elastic_ipv4 = nixops.util.attr_property("ec2.elasticIpv4", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    zone = nixops.util.attr_property("ec2.zone", None)
    controller = nixops.util.attr_property("ec2.controller", None)  # FIXME: not used
    ami = nixops.util.attr_property("ec2.ami", None)
    instance_type = nixops.util.attr_property("ec2.instanceType", None)
    key_pair = nixops.util.attr_property("ec2.keyPair", None)
    public_host_key = nixops.util.attr_property("ec2.publicHostKey", None)
    private_host_key = nixops.util.attr_property("ec2.privateHostKey", None)
    private_key_file = nixops.util.attr_property("ec2.privateKeyFile", None)
    instance_profile = nixops.util.attr_property("ec2.instanceProfile", None)
    security_groups = nixops.util.attr_property("ec2.securityGroups", None, 'json')
    tags = nixops.util.attr_property("ec2.tags", {}, 'json')
    block_device_mapping = nixops.util.attr_property("ec2.blockDeviceMapping", {}, 'json')
    root_device_type = nixops.util.attr_property("ec2.rootDeviceType", None)
    backups = nixops.util.attr_property("ec2.backups", {}, 'json')
    dns_hostname = nixops.util.attr_property("route53.hostName", None)
    dns_ttl = nixops.util.attr_property("route53.ttl", None, int)
    route53_access_key_id = nixops.util.attr_property("route53.accessKeyId", None)
    client_token = nixops.util.attr_property("ec2.clientToken", None)
    spot_instance_request_id = nixops.util.attr_property("ec2.spotInstanceRequestId", None)
    spot_instance_price = nixops.util.attr_property("ec2.spotInstancePrice", None)

    def __init__(self, depl, name, id):
        MachineState.__init__(self, depl, name, id)
        self._conn = None
        self._conn_route53 = None


    def _reset_state(self):
        """Discard all state pertaining to an instance."""
        with self.depl._db:
            self.state = MachineState.MISSING
            self.vm_id = None
            self.public_ipv4 = None
            self.private_ipv4 = None
            self.elastic_ipv4 = None
            self.region = None
            self.zone = None
            self.controller = None
            self.ami = None
            self.instance_type = None
            self.key_pair = None
            self.public_host_key = None
            self.private_host_key = None
            self.instance_profile = None
            self.security_groups = None
            self.tags = {}
            self.block_device_mapping = {}
            self.root_device_type = None
            self.backups = {}
            self.dns_hostname = None
            self.dns_ttl = None


    def get_ssh_name(self):
        if not self.public_ipv4:
            raise Exception("EC2 machine ‘{0}’ does not have a public IPv4 address (yet)".format(self.name))
        return self.public_ipv4


    def get_ssh_private_key_file(self):
        if self.private_key_file: return self.private_key_file
        if self._ssh_private_key_file: return self._ssh_private_key_file
        for r in self.depl.active_resources.itervalues():
            if isinstance(r, nixops.resources.ec2_keypair.EC2KeyPairState) and \
                    r.state == nixops.resources.ec2_keypair.EC2KeyPairState.UP and \
                    r.keypair_name == self.key_pair:
                return self.write_ssh_private_key(r.private_key)
        return None


    def get_ssh_flags(self):
        file = self.get_ssh_private_key_file()
        return ["-i", file] if file else []


    def get_physical_spec(self):
        block_device_mapping = {}
        for k, v in self.block_device_mapping.items():
            if (v.get('encrypt', False)
                and v.get('passphrase', "") == ""
                and v.get('generatedKey', "") != ""):
                block_device_mapping[_sd_to_xvd(k)] = {
                    'passphrase': Function("pkgs.lib.mkOverride 10",
                                           v['generatedKey'], call=True),
                }

        return {
            'require': [
                RawValue("<nixpkgs/nixos/modules/virtualisation/amazon-config.nix>")
            ],
            ('deployment', 'ec2', 'blockDeviceMapping'): block_device_mapping,
            ('deployment', 'ec2', 'instanceId'): self.vm_id,
        }

    def get_physical_backup_spec(self, backupid):
        val = {}
        if backupid in self.backups:
            for dev, snap in self.backups[backupid].items():
                if not dev.startswith("/dev/sda"):
                    val[_sd_to_xvd(dev)] = { 'disk': Function("pkgs.lib.mkOverride 10", snap, call=True)}
            val = { ('deployment', 'ec2', 'blockDeviceMapping'): val }
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
                keys["luks-" + _sd_to_xvd(k).replace('/dev/', '')] = v['generatedKey']
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


    def disk_volume_options(self, v):
        if v['iops'] != 0 and not v['iops'] is None:
            iops = v['iops']
            volume_type = 'io1'
        else:
            iops = None
            volume_type = 'standard'
        return (volume_type, iops)


    def connect(self):
        if self._conn: return self._conn
        self._conn = nixops.ec2_utils.connect(self.region, self.access_key_id)
        return self._conn


    def connect_route53(self):
        if self._conn_route53:
            return

        # Get the secret access key from the environment or from ~/.ec2-keys.
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.route53_access_key_id)

        self._conn_route53 = boto.connect_route53(access_key_id, secret_access_key)

    def _get_spot_instance_request_by_id(self, request_id, allow_missing=False):
        """Get spot instance request object by id."""
        self.connect()
        result = self._conn.get_all_spot_instance_requests([request_id])
        if len(result) == 0:
            if allow_missing:
                return None
            raise EC2InstanceDisappeared("Spot instance request ‘{0}’ disappeared!".format(request_id))
        return result[0]


    def _get_instance_by_id(self, instance_id, allow_missing=False):
        """Get instance object by instance id."""
        self.connect()
        reservations = self._conn.get_all_instances([instance_id])
        if len(reservations) == 0:
            if allow_missing:
                return None
            raise EC2InstanceDisappeared("EC2 instance ‘{0}’ disappeared!".format(instance_id))
        return reservations[0].instances[0]


    def _get_snapshot_by_id(self, snapshot_id):
        """Get snapshot object by instance id."""
        self.connect()
        snapshots = self._conn.get_all_snapshots([snapshot_id])
        if len(snapshots) != 1:
            raise Exception("unable to find snapshot ‘{0}’".format(snapshot_id))
        return snapshots[0]


    def _wait_for_ip(self, instance):
        self.log_start("waiting for IP address... ".format(self.name))

        while True:
            instance.update()
            self.log_continue("[{0}] ".format(instance.state))
            if instance.state not in {"pending", "running", "scheduling", "launching", "stopped"}:
                raise Exception("EC2 instance ‘{0}’ failed to start (state is ‘{1}’)".format(self.vm_id, instance.state))
            if instance.state != "running":
                time.sleep(3)
                continue
            if instance.ip_address:
                break
            time.sleep(3)

        self.log_end("{0} / {1}".format(instance.ip_address, instance.private_ip_address))

        nixops.known_hosts.add(instance.ip_address, self.public_host_key)

        self.private_ipv4 = instance.private_ip_address
        self.public_ipv4 = instance.ip_address
        self.ssh_pinged = False


    def _booted_from_ebs(self):
        return self.root_device_type == "ebs"

    def update_block_device_mapping(self, k, v):
        x = self.block_device_mapping
        if v == None:
            x.pop(k, None)
        else:
            x[k] = v
        self.block_device_mapping = x


    def get_backups(self):
        self.connect()
        backups = {}
        current_volumes = set([v['volumeId'] for v in self.block_device_mapping.values()])
        for b_id, b in self.backups.items():
            backups[b_id] = {}
            backup_status = "complete"
            info = []
            for k, v in self.block_device_mapping.items():
                if not k in b.keys():
                    backup_status = "incomplete"
                    info.append("{0} - {1} - Not available in backup".format(self.name, _sd_to_xvd(k)))
                else:
                    snapshot_id = b[k]
                    try:
                        snapshot = self._get_snapshot_by_id(snapshot_id)
                        snapshot_status = snapshot.update()
                        info.append("progress[{0},{1},{2}] = {3}".format(self.name, _sd_to_xvd(k), snapshot_id, snapshot_status))
                        if snapshot_status != '100%':
                            backup_status = "running"
                    except boto.exception.EC2ResponseError as e:
                        if e.error_code != "InvalidSnapshot.NotFound": raise
                        info.append("{0} - {1} - {2} - Snapshot has disappeared".format(self.name, _sd_to_xvd(k), snapshot_id))
                        backup_status = "unavailable"
            backups[b_id]['status'] = backup_status
            backups[b_id]['info'] = info
        return backups


    def remove_backup(self, backup_id):
        self.log('removing backup {0}'.format(backup_id))
        self.connect()
        _backups = self.backups
        if not backup_id in _backups.keys():
            self.warn('backup {0} not found, skipping'.format(backup_id))
        else:
            for dev, snapshot_id in _backups[backup_id].items():
                snapshot = None
                try:
                    snapshot = self._get_snapshot_by_id(snapshot_id)
                except:
                    self.warn('snapshot {0} not found, skipping'.format(snapshot_id))
                if not snapshot is None:
                    self.log('removing snapshot {0}'.format(snapshot_id))
                    nixops.ec2_utils.retry(lambda: snapshot.delete())

            _backups.pop(backup_id)
            self.backups = _backups


    def get_common_tags(self):
        return {'CharonNetworkUUID': self.depl.uuid,
                'CharonMachineName': self.name,
                'CharonStateFile': "{0}@{1}:{2}".format(getpass.getuser(), socket.gethostname(), self.depl._db.db_file)}

    def backup(self, defn, backup_id):
        self.connect()

        self.log("backing up machine ‘{0}’ using id ‘{1}’".format(self.name, backup_id))
        backup = {}
        _backups = self.backups
        for k, v in self.block_device_mapping.items():
            snapshot = nixops.ec2_utils.retry(lambda: self._conn.create_snapshot(volume_id=v['volumeId']))
            self.log("+ created snapshot of volume ‘{0}’: ‘{1}’".format(v['volumeId'], snapshot.id))

            snapshot_tags = {}
            snapshot_tags.update(defn.tags)
            snapshot_tags.update(self.get_common_tags())
            snapshot_tags['Name'] = "{0} - {3} [{1} - {2}]".format(self.depl.description, self.name, k, backup_id)

            nixops.ec2_utils.retry(lambda: self._conn.create_tags([snapshot.id], snapshot_tags))
            backup[k] = snapshot.id
        _backups[backup_id] = backup
        self.backups = _backups


    def restore(self, defn, backup_id, devices=[]):
        self.stop()

        self.log("restoring machine ‘{0}’ to backup ‘{1}’".format(self.name, backup_id))
        for d in devices:
            self.log(" - {0}".format(d))

        for k, v in self.block_device_mapping.items():
            if devices == [] or _sd_to_xvd(k) in devices:
                # detach disks
                volume = nixops.ec2_utils.get_volume_by_id(self.connect(), v['volumeId'])
                if volume and volume.update() == "in-use":
                    self.log("detaching volume from ‘{0}’".format(self.name))
                    volume.detach()

                # attach backup disks
                snapshot_id = self.backups[backup_id][k]
                self.log("creating volume from snapshot ‘{0}’".format(snapshot_id))
                new_volume = self._conn.create_volume(size=0, snapshot=snapshot_id, zone=self.zone)

                # check if original volume is available, aka detached from the machine
                self.wait_for_volume_available(volume)
                # check if new volume is available
                self.wait_for_volume_available(new_volume)

                self.log("attaching volume ‘{0}’ to ‘{1}’".format(new_volume.id, self.name))
                new_volume.attach(self.vm_id, k)
                new_v = self.block_device_mapping[k]
                if v.get('partOfImage', False) or v.get('charonDeleteOnTermination', False) or v.get('deleteOnTermination', False):
                    new_v['charonDeleteOnTermination'] = True
                    self._delete_volume(v['volumeId'], True)
                new_v['volumeId'] = new_volume.id
                self.update_block_device_mapping(k, new_v)


    def create_after(self, resources):
        # EC2 instances can require key pairs, IAM roles, security
        # groups, EBS volumes and elastic IPs.  FIXME: only depend on
        # the specific key pair / role needed for this instance.
        return {r for r in resources if
                isinstance(r, nixops.resources.ec2_keypair.EC2KeyPairState) or
                isinstance(r, nixops.resources.iam_role.IAMRoleState) or
                isinstance(r, nixops.resources.ec2_security_group.EC2SecurityGroupState) or
                isinstance(r, nixops.resources.ebs_volume.EBSVolumeState) or
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState)}


    def attach_volume(self, device, volume_id):
        volume = nixops.ec2_utils.get_volume_by_id(self.connect(), volume_id)
        if volume.status == "in-use" and \
            self.vm_id != volume.attach_data.instance_id and \
            self.depl.logger.confirm("volume ‘{0}’ is in use by instance ‘{1}’, "
                                     "are you sure you want to attach this volume?".format(volume_id, volume.attach_data.instance_id)):

            self.log_start("detaching volume ‘{0}’ from instance ‘{1}’...".format(volume_id, volume.attach_data.instance_id))
            volume.detach()

            def check_available():
                res = volume.update()
                self.log_continue("[{0}] ".format(res))
                return res == 'available'

            nixops.util.check_wait(check_available)
            self.log_end('')

            if volume.update() != "available":
                self.log("force detaching volume ‘{0}’ from instance ‘{1}’...".format(volume_id, volume.attach_data.instance_id))
                volume.detach(True)
                nixops.util.check_wait(check_available)

        self.log_start("attaching volume ‘{0}’ as ‘{1}’...".format(volume_id, _sd_to_xvd(device)))
        if self.vm_id != volume.attach_data.instance_id:
            # Attach it.
            self._conn.attach_volume(volume_id, self.vm_id, device)

        def check_attached():
            volume.update()
            res = volume.attach_data.status
            self.log_continue("[{0}] ".format(res))
            return res == 'attached'

        # If volume is not in attached state, wait for it before going on.
        if volume.attach_data.status != "attached":
            nixops.util.check_wait(check_attached)

        # Wait until the device is visible in the instance.
        def check_dev():
            res = self.run_command("test -e {0}".format(_sd_to_xvd(device)), check=False)
            return res == 0
        nixops.util.check_wait(check_dev)

        self.log_end('')


    def wait_for_volume_available(self, volume):
        def check_available():
            res = volume.update()
            self.log_continue("[{0}] ".format(res))
            return res == 'available'

        nixops.util.check_wait(check_available, max_tries=90)
        self.log_end('')


    def assign_elastic_ip(self, elastic_ipv4, instance, check):
        # Assign or release an elastic IP address, if given.
        if (self.elastic_ipv4 or "") != elastic_ipv4 or (instance.ip_address != elastic_ipv4) or check:
            if elastic_ipv4 != "":
                # wait until machine is in running state
                self.log_start("waiting for machine to be in running state... ".format(self.name))
                while True:
                    self.log_continue("[{0}] ".format(instance.state))
                    if instance.state == "running":
                        break
                    if instance.state not in {"running", "pending"}:
                        raise Exception(
                            "EC2 instance ‘{0}’ failed to reach running state (state is ‘{1}’)"
                            .format(self.vm_id, instance.state))
                    time.sleep(3)
                    instance.update()
                self.log_end("")

                addresses = self._conn.get_all_addresses(addresses=[elastic_ipv4])
                if addresses[0].instance_id != "" \
                    and addresses[0].instance_id != self.vm_id \
                    and not self.depl.logger.confirm(
                        "are you sure you want to associate IP address ‘{0}’, which is currently in use by instance ‘{1}’?".format(
                            elastic_ipv4, addresses[0].instance_id)):
                    raise Exception("elastic IP ‘{0}’ already in use...".format(elastic_ipv4))
                else:
                    self.log("associating IP address ‘{0}’...".format(elastic_ipv4))
                    addresses[0].associate(self.vm_id)
                    self.log_start("waiting for address to be associated with this machine... ")
                    instance.update()
                    while True:
                        self.log_continue("[{0}] ".format(instance.ip_address))
                        if instance.ip_address == elastic_ipv4:
                            break
                        time.sleep(3)
                        instance.update()
                    self.log_end("")

                nixops.known_hosts.add(elastic_ipv4, self.public_host_key)
                with self.depl._db:
                    self.elastic_ipv4 = elastic_ipv4
                    self.public_ipv4 = elastic_ipv4
                    self.ssh_pinged = False

            elif self.elastic_ipv4 != None:
                self.log("disassociating IP address ‘{0}’...".format(self.elastic_ipv4))
                self._conn.disassociate_address(public_ip=self.elastic_ipv4)
                with self.depl._db:
                    self.elastic_ipv4 = None
                    self.public_ipv4 = None
                    self.ssh_pinged = False



    def create_instance(self, defn, zone, devmap, user_data, ebs_optimized):
        common_args = dict(
            instance_type=defn.instance_type,
            placement=zone,
            key_name=defn.key_pair,
            security_groups=defn.security_groups,
            block_device_map=devmap,
            user_data=user_data,
            image_id=defn.ami,
            ebs_optimized=ebs_optimized
        )
        if defn.instance_profile.startswith("arn:") :
            common_args['instance_profile_arn'] = defn.instance_profile
        else:
            common_args['instance_profile_name'] = defn.instance_profile

        if defn.spot_instance_price:
            request = nixops.ec2_utils.retry(
                lambda: self._conn.request_spot_instances(price=defn.spot_instance_price/100.0, **common_args)
            )[0]

            common_tags = self.get_common_tags()
            tags = {'Name': "{0} [{1}]".format(self.depl.description, self.name)}
            tags.update(defn.tags)
            tags.update(common_tags)
            nixops.ec2_utils.retry(lambda: self._conn.create_tags([request.id], tags))

            self.spot_instance_price = defn.spot_instance_price
            self.spot_instance_request_id = request.id

            self.log_start("Waiting for spot instance request to be fulfilled. ")
            def check_request():
                req = self._get_spot_instance_request_by_id(request.id)
                self.log_continue("[{0}] ".format(req.status.code))
                return req.status.code == "fulfilled"
            self.log_end("")

            try:
                nixops.util.check_wait(test=check_request)
            finally:
                # cancel spot instance request, it isn't needed after instance is provisioned
                self.spot_instance_request_id = None
                self._conn.cancel_spot_instance_requests([request.id])

            request = self._get_spot_instance_request_by_id(request.id)

            instance = nixops.ec2_utils.retry(lambda: self._get_instance_by_id(request.instance_id))

            return instance
        else:
            reservation = nixops.ec2_utils.retry(lambda: self._conn.run_instances(
                client_token=self.client_token, **common_args), error_codes = ['InvalidParameterValue', 'UnauthorizedOperation' ])

            assert len(reservation.instances) == 1
            return reservation.instances[0]

    def after_activation(self, defn):
        # Detach volumes that are no longer in the deployment spec.
        for k, v in self.block_device_mapping.items():
            if k not in defn.block_device_mapping and not v.get('partOfImage', False):
                if v['disk'].startswith("ephemeral"):
                    raise Exception("cannot detach ephemeral device ‘{0}’ from EC2 instance ‘{1}’"
                    .format(_sd_to_xvd(k), self.name))

                assert v.get('volumeId', None)

                self.log("detaching device ‘{0}’...".format(_sd_to_xvd(k)))
                volumes = self._conn.get_all_volumes([],
                    filters={'attachment.instance-id': self.vm_id, 'attachment.device': k, 'volume-id': v['volumeId']})
                assert len(volumes) <= 1

                if len(volumes) == 1:
                    device = _sd_to_xvd(k)
                    if v.get('encrypt', False):
                        dm = device.replace("/dev/", "/dev/mapper/")
                        self.run_command("umount -l {0}".format(dm), check=False)
                        self.run_command("cryptsetup luksClose {0}".format(device.replace("/dev/", "")), check=False)
                    else:
                        self.run_command("umount -l {0}".format(device), check=False)
                    if not self._conn.detach_volume(volumes[0].id, instance_id=self.vm_id, device=k):
                        raise Exception("unable to detach device ‘{0}’ from EC2 machine ‘{1}’".format(v['disk'], self.name))
                        # FIXME: Wait until the volume is actually detached.

                if v.get('charonDeleteOnTermination', False) or v.get('deleteOnTermination', False):
                    self._delete_volume(v['volumeId'])

                self.update_block_device_mapping(k, None)


    def create(self, defn, check, allow_reboot, allow_recreate):
        assert isinstance(defn, EC2Definition)
        assert defn.type == "ec2"

        if self.state != self.UP:
            check = True

        self.set_common_state(defn)

        # Figure out the access key.
        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘deployment.ec2.accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self.private_key_file = defn.private_key or None
        self.owners = defn.owners

        # Stop the instance (if allowed) to change instance attributes
        # such as the type.
        if self.vm_id and allow_reboot and self._booted_from_ebs() and self.instance_type != defn.instance_type:
            self.stop()
            check = True

        # Check whether the instance hasn't been killed behind our
        # backs.  Restart stopped instances.
        if self.vm_id and check:
            self.connect()
            instance = self._get_instance_by_id(self.vm_id, allow_missing=True)
            if instance is None or instance.state in {"shutting-down", "terminated"}:
                if not allow_recreate:
                    raise Exception("EC2 instance ‘{0}’ went away; use ‘--allow-recreate’ to create a new one".format(self.name))
                self.log("EC2 instance went away (state ‘{0}’), will recreate".format(instance.state if instance else "gone"))
                self._reset_state()
            elif instance.state == "stopped":
                self.log("EC2 instance was stopped, restarting...")

                # Modify the instance type, if desired.
                if self.instance_type != defn.instance_type:
                    self.log("changing instance type from ‘{0}’ to ‘{1}’...".format(self.instance_type, defn.instance_type))
                    instance.modify_attribute("instanceType", defn.instance_type)
                    self.instance_type = defn.instance_type

                # When we restart, we'll probably get a new IP.  So forget the current one.
                self.public_ipv4 = None
                self.private_ipv4 = None

                instance.start()

                self.state = self.STARTING

        resize_root = False

        # Create the instance.
        if not self.vm_id:
            self.log("creating EC2 instance (AMI ‘{0}’, type ‘{1}’, region ‘{2}’)...".format(
                defn.ami, defn.instance_type, defn.region))
            if not self.client_token: self._reset_state()

            self.region = defn.region
            self.connect()

            # Figure out whether this AMI is EBS-backed.
            ami = self._conn.get_all_images([defn.ami])[0]
            self.root_device_type = ami.root_device_type

            # Check if we need to resize the root disk
            resize_root = defn.root_disk_size != 0 and ami.root_device_type == 'ebs'

            # Set the initial block device mapping to the ephemeral
            # devices defined in the spec.  These cannot be changed
            # later.
            devmap = boto.ec2.blockdevicemapping.BlockDeviceMapping()
            devs_mapped = {}
            for k, v in defn.block_device_mapping.iteritems():
                if re.match("/dev/sd[a-e]", k) and not v['disk'].startswith("ephemeral"):
                    raise Exception("non-ephemeral disk not allowed on device ‘{0}’; use /dev/xvdf or higher".format(_sd_to_xvd(k)))
                if v['disk'].startswith("ephemeral"):
                    devmap[k] = boto.ec2.blockdevicemapping.BlockDeviceType(ephemeral_name=v['disk'])
                    self.update_block_device_mapping(k, v)

            root_device = ami.root_device_name
            if resize_root:
                devmap[root_device] = ami.block_device_mapping[root_device]
                devmap[root_device].size = defn.root_disk_size

            # If we're attaching any EBS volumes, then make sure that
            # we create the instance in the right placement zone.
            zone = defn.zone or None
            for k, v in defn.block_device_mapping.iteritems():
                if not v['disk'].startswith("vol-"): continue
                # Make note of the placement zone of the volume.
                volume = nixops.ec2_utils.get_volume_by_id(self.connect(), v['disk'])
                if not zone:
                    self.log("starting EC2 instance in zone ‘{0}’ due to volume ‘{1}’".format(
                            volume.zone, v['disk']))
                    zone = volume.zone
                elif zone != volume.zone:
                    raise Exception("unable to start EC2 instance ‘{0}’ in zone ‘{1}’ because volume ‘{2}’ is in zone ‘{3}’"
                                    .format(self.name, zone, v['disk'], volume.zone))

            # Do we want an EBS-optimized instance?
            prefer_ebs_optimized = False
            for k, v in defn.block_device_mapping.iteritems():
                (volume_type, iops) = self.disk_volume_options(v)
                if volume_type != "standard": prefer_ebs_optimized = True

            # if we have PIOPS volume and instance type supports EBS Optimized flags, then use ebs_optimized
            ebs_optimized = prefer_ebs_optimized and defn.ebs_optimized

            # Generate a public/private host key.
            if not self.public_host_key:
                (private, public) = nixops.util.create_key_pair(type='dsa')
                with self.depl._db:
                    self.public_host_key = public
                    self.private_host_key = private

            user_data = "SSH_HOST_DSA_KEY_PUB:{0}\nSSH_HOST_DSA_KEY:{1}\n".format(
                self.public_host_key, self.private_host_key.replace("\n", "|"))

            # Use a client token to ensure that instance creation is
            # idempotent; i.e., if we get interrupted before recording
            # the instance ID, we'll get the same instance ID on the
            # next run.
            if not self.client_token:
                with self.depl._db:
                    self.client_token = nixops.util.generate_random_string(length=48) # = 64 ASCII chars
                    self.state = self.STARTING

            instance = self.create_instance(defn, zone, devmap, user_data, ebs_optimized)

            with self.depl._db:
                self.vm_id = instance.id
                self.controller = defn.controller
                self.ami = defn.ami
                self.instance_type = defn.instance_type
                self.key_pair = defn.key_pair
                self.security_groups = defn.security_groups
                self.zone = instance.placement
                self.client_token = None
                self.private_host_key = None

        # There is a short time window during which EC2 doesn't
        # know the instance ID yet.  So wait until it does.
        while True:
            try:
                instance = self._get_instance_by_id(self.vm_id)
                break
            except EC2InstanceDisappeared:
                pass
            except boto.exception.EC2ResponseError as e:
                if e.error_code != "InvalidInstanceID.NotFound":
                    raise
            self.log("EC2 instance ‘{0}’ not known yet, waiting...".format(self.vm_id))
            time.sleep(3)

        # Warn about some EC2 options that we cannot update for an existing instance.
        if self.instance_type != defn.instance_type:
            self.warn("cannot change type of a running instance (use ‘--allow-reboot’)")
        if self.region != defn.region:
            self.warn("cannot change region of a running instance")
        if defn.zone and self.zone != defn.zone:
            self.warn("cannot change availability zone of a running instance")
        instance_groups = set([g.name for g in instance.groups])
        if set(defn.security_groups) != instance_groups:
            self.warn(
                'cannot change security groups of an existing instance (from [{0}] to [{1}])'.format(
                    ", ".join(set(defn.security_groups)),
                    ", ".join(instance_groups))
            )

        # Reapply tags if they have changed.
        common_tags = self.get_common_tags()

        if self.owners != []:
            common_tags['Owners'] = ", ".join(self.owners)

        tags = {'Name': "{0} [{1}]".format(self.depl.description, self.name)}
        tags.update(defn.tags)
        tags.update(common_tags)
        if check or self.tags != tags:
            nixops.ec2_utils.retry(lambda: self._conn.create_tags([self.vm_id], tags))
            # TODO: remove obsolete tags?
            self.tags = tags

        # Assign the elastic IP.  If necessary, dereference the resource.
        elastic_ipv4 = defn.elastic_ipv4
        if elastic_ipv4.startswith("res-"):
            res = self.depl.get_typed_resource(elastic_ipv4[4:], "elastic-ip")
            elastic_ipv4 = res.public_ipv4
        self.assign_elastic_ip(elastic_ipv4, instance, check)

        # Wait for the IP address.
        if not self.public_ipv4 or check:
            instance = self._get_instance_by_id(self.vm_id)
            self._wait_for_ip(instance)

        if defn.dns_hostname:
            self._update_route53(defn)

        # Wait until the instance is reachable via SSH.
        self.wait_for_ssh(check=check)

        if resize_root:
            self.log('resizing root disk...')
            self.run_command("resize2fs {0}".format(_sd_to_xvd(root_device)))

        # Add disks that were in the original device mapping of image.
        for k, dm in instance.block_device_mapping.items():
            if k not in self.block_device_mapping and dm.volume_id:
                bdm = {'volumeId': dm.volume_id, 'partOfImage': True}
                self.update_block_device_mapping(k, bdm)

        # Detect if volumes were manually detached.  If so, reattach
        # them.
        for k, v in self.block_device_mapping.items():
            if k not in instance.block_device_mapping.keys() and not v.get('needsAttach', False) and v.get('volumeId', None):
                self.warn("device ‘{0}’ was manually detached!".format(_sd_to_xvd(k)))
                v['needsAttach'] = True
                self.update_block_device_mapping(k, v)

        # Detect if volumes were manually destroyed.
        for k, v in self.block_device_mapping.items():
            if v.get('needsAttach', False):
                print v['volumeId']
                volume = nixops.ec2_utils.get_volume_by_id(self.connect(), v['volumeId'], allow_missing=True)
                if volume: continue
                if not allow_recreate:
                    raise Exception("volume ‘{0}’ (used by EC2 instance ‘{1}’) no longer exists; "
                                    "run ‘nixops stop’, then ‘nixops deploy --allow-recreate’ to create a new, empty volume"
                                    .format(v['volumeId'], self.name))
                self.warn("volume ‘{0}’ has disappeared; will create an empty volume to replace it".format(v['volumeId']))
                self.update_block_device_mapping(k, None)

        # Create missing volumes.
        for k, v in defn.block_device_mapping.iteritems():

            volume = None
            if v['disk'] == '':
                if k in self.block_device_mapping: continue
                self.log("creating EBS volume of {0} GiB...".format(v['size']))
                (volume_type, iops) = self.disk_volume_options(v)
                volume = self._conn.create_volume(size=v['size'], zone=self.zone, volume_type=volume_type, iops=iops)
                v['volumeId'] = volume.id

            elif v['disk'].startswith("vol-"):
                if k in self.block_device_mapping:
                    cur_volume_id = self.block_device_mapping[k]['volumeId']
                    if cur_volume_id != v['disk']:
                        raise Exception("cannot attach EBS volume ‘{0}’ to ‘{1}’ because volume ‘{2}’ is already attached there".format(v['disk'], k, cur_volume_id))
                    continue
                v['volumeId'] = v['disk']

            elif v['disk'].startswith("res-"):
                res_name = v['disk'][4:]
                res = self.depl.get_typed_resource(res_name, "ebs-volume")
                if res.state != self.UP:
                    raise Exception("EBS volume ‘{0}’ has not been created yet".format(res_name))
                assert res.volume_id
                if k in self.block_device_mapping:
                    cur_volume_id = self.block_device_mapping[k]['volumeId']
                    if cur_volume_id != res.volume_id:
                        raise Exception("cannot attach EBS volume ‘{0}’ to ‘{1}’ because volume ‘{2}’ is already attached there".format(res_name, k, cur_volume_id))
                    continue
                v['volumeId'] = res.volume_id

            elif v['disk'].startswith("snap-"):
                if k in self.block_device_mapping: continue
                self.log("creating volume from snapshot ‘{0}’...".format(v['disk']))
                (volume_type, iops) = self.disk_volume_options(v)
                volume = self._conn.create_volume(size=0, snapshot=v['disk'], zone=self.zone, volume_type=volume_type, iops=iops)
                v['volumeId'] = volume.id

            else:
                raise Exception("adding device mapping ‘{0}’ to a running instance is not (yet) supported".format(v['disk']))

            # ‘charonDeleteOnTermination’ denotes whether we have to
            # delete the volume.  This is distinct from
            # ‘deleteOnTermination’ for backwards compatibility with
            # the time that we still used auto-created volumes.
            v['charonDeleteOnTermination'] = v['deleteOnTermination']
            v['needsAttach'] = True
            self.update_block_device_mapping(k, v)

            # Wait for volume to get to available state for newly
            # created volumes only (EC2 sometimes returns weird
            # temporary states for newly created volumes, e.g. shortly
            # in-use).  Doing this after updating the device mapping
            # state, to make it recoverable in case an exception
            # happens (e.g. in other machine's deployments).
            if volume: self.wait_for_volume_available(volume)

        # Always apply tags to all volumes
        for k, v in self.block_device_mapping.items():
            # Tag the volume.
            volume_tags = {}
            volume_tags.update(common_tags)
            volume_tags.update(defn.tags)
            volume_tags['Name'] = "{0} [{1} - {2}]".format(self.depl.description, self.name, _sd_to_xvd(k))
            if 'disk' in v and not v['disk'].startswith("ephemeral"):
                nixops.ec2_utils.retry(lambda: self._conn.create_tags([v['volumeId']], volume_tags))

        # Attach missing volumes.
        for k, v in self.block_device_mapping.items():
            if v.get('needsAttach', False):
                self.attach_volume(k, v['volumeId'])
                del v['needsAttach']
                self.update_block_device_mapping(k, v)

        # FIXME: process changes to the deleteOnTermination flag.

        # Auto-generate LUKS keys if the model didn't specify one.
        for k, v in self.block_device_mapping.items():
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") == "":
                v['generatedKey'] = nixops.util.generate_random_string(length=256)
                self.update_block_device_mapping(k, v)


    def _update_route53(self, defn):
        import boto.route53
        import boto.route53.record

        self.dns_hostname = defn.dns_hostname
        self.dns_ttl = defn.dns_ttl
        self.route53_access_key_id = defn.route53_access_key_id

        self.log('sending Route53 DNS: {0} {1}'.format(self.public_ipv4, self.dns_hostname))

        self.connect_route53()

        hosted_zone = ".".join(self.dns_hostname.split(".")[1:])
        zones = self._conn_route53.get_all_hosted_zones()

        def testzone(hosted_zone, zone):
            """returns True if there is a subcomponent match"""
            hostparts = hosted_zone.split(".")
            zoneparts = zone.Name.split(".")[:-1] # strip the last ""

            return hostparts[::-1][:len(zoneparts)][::-1] == zoneparts

        zones = [zone for zone in zones['ListHostedZonesResponse']['HostedZones'] if testzone(hosted_zone, zone)]
        if len(zones) == 0:
            raise Exception('hosted zone for {0} not found'.format(hosted_zone))

        zones = sorted(zones, cmp=lambda a, b: cmp(len(a), len(b)), reverse=True)
        zoneid = zones[0]['Id'].split("/")[2]

        # name argument does not filter, just is a starting point, annoying.. copying into a separate list
        all_prevrrs = self._conn_route53.get_all_rrsets(hosted_zone_id=zoneid, type="A", name="{0}.".format(self.dns_hostname))
        prevrrs = []
        for prevrr in all_prevrrs:
            if prevrr.name == "{0}.".format(self.dns_hostname):
                prevrrs.append(prevrr)

        changes = boto.route53.record.ResourceRecordSets(connection=self._conn_route53, hosted_zone_id=zoneid)
        if len(prevrrs) > 0:
            for prevrr in prevrrs:
                change = changes.add_change("DELETE", self.dns_hostname, "A")
                change.add_value(",".join(prevrr.resource_records))

        change = changes.add_change("CREATE", self.dns_hostname, "A")
        change.add_value(self.public_ipv4)
        self._commit_route53_changes(changes)


    def _commit_route53_changes(self, changes):
        """Commit changes, but retry PriorRequestNotComplete errors."""
        retry = 3
        while True:
            try:
                retry -= 1
                return changes.commit()
            except boto.route53.exception.DNSServerError, e:
                code = e.body.split("<Code>")[1]
                code = code.split("</Code>")[0]
                if code != 'PriorRequestNotComplete' or retry < 0:
                    raise e
                time.sleep(1)


    def _delete_volume(self, volume_id, allow_keep=False):
        if not self.depl.logger.confirm("are you sure you want to destroy EC2 volume ‘{0}’?".format(volume_id)):
            if allow_keep:
                return
            else:
                raise Exception("not destroying EC2 volume ‘{0}’".format(volume_id))
        self.log("destroying EC2 volume ‘{0}’...".format(volume_id))
        volume = nixops.ec2_utils.get_volume_by_id(self.connect(), volume_id, allow_missing=True)
        if not volume: return
        nixops.util.check_wait(lambda: volume.update() == 'available')
        volume.delete()


    def destroy(self, wipe=False):
        if not (self.vm_id or self.client_token): return True
        if not self.depl.logger.confirm("are you sure you want to destroy EC2 machine ‘{0}’?".format(self.name)): return False

        self.log_start("destroying EC2 machine... ".format(self.name))

        # Find the instance, either by its ID or by its client token.
        # The latter allows us to destroy instances that were "leaked"
        # in create() due to it being interrupted after the instance
        # was created but before it registered the ID in the database.
        self.connect()
        instance = None
        if self.vm_id:
            instance = self._get_instance_by_id(self.vm_id, allow_missing=True)
        else:
            reservations = self._conn.get_all_instances(filters={'client-token': self.client_token})
            if len(reservations) > 0:
                instance = reservations[0].instances[0]

        if instance:
            instance.terminate()

            # Wait until it's really terminated.
            while True:
                self.log_continue("[{0}] ".format(instance.state))
                if instance.state == "terminated": break
                time.sleep(3)
                instance.update()

        self.log_end("")

        # Destroy volumes created for this instance.
        for k, v in self.block_device_mapping.items():
            if v.get('charonDeleteOnTermination', False):
                self._delete_volume(v['volumeId'])
                self.update_block_device_mapping(k, None)

        return True


    def stop(self):
        if not self._booted_from_ebs():
            self.warn("cannot stop non-EBS-backed instance")
            return

        self.log_start("stopping EC2 machine... ")

        instance = self._get_instance_by_id(self.vm_id)
        instance.stop()  # no-op if the machine is already stopped

        self.state = self.STOPPING

        # Wait until it's really stopped.
        def check_stopped():
            self.log_continue("[{0}] ".format(instance.state))
            if instance.state == "stopped":
                return True
            if instance.state not in {"running", "stopping"}:
                raise Exception(
                    "EC2 instance ‘{0}’ failed to stop (state is ‘{1}’)"
                    .format(self.vm_id, instance.state))
            instance.update()
            return False

        if not nixops.util.check_wait(check_stopped, initial=3, max_tries=300, exception=False): # = 15 min
            # If stopping times out, then do an unclean shutdown.
            self.log_end("(timed out)")
            self.log_start("force-stopping EC2 machine... ")
            instance.stop(force=True)
            if not nixops.util.check_wait(check_stopped, initial=3, max_tries=100, exception=False): # = 5 min
                # Amazon docs suggest doing a force stop twice...
                self.log_end("(timed out)")
                self.log_start("force-stopping EC2 machine... ")
                instance.stop(force=True)
                nixops.util.check_wait(check_stopped, initial=3, max_tries=100) # = 5 min

        self.log_end("")

        self.state = self.STOPPED
        self.ssh_master = None


    def start(self):
        if not self._booted_from_ebs():
            return

        self.log("starting EC2 machine...")

        instance = self._get_instance_by_id(self.vm_id)
        instance.start()  # no-op if the machine is already started

        self.state = self.STARTING

        # Wait until it's really started, and obtain its new IP
        # address.  Warn the user if the IP address has changed (which
        # is generally the case).
        prev_private_ipv4 = self.private_ipv4
        prev_public_ipv4 = self.public_ipv4

        if self.elastic_ipv4:
            self.log("restoring previously attached elastic IP")
            self.assign_elastic_ip(self.elastic_ipv4, instance, True)

        self._wait_for_ip(instance)

        if prev_private_ipv4 != self.private_ipv4 or prev_public_ipv4 != self.public_ipv4:
            self.warn("IP address has changed, you may need to run ‘nixops deploy’")

        self.wait_for_ssh(check=True)
        self.send_keys()


    def _check(self, res):
        if not self.vm_id:
            res.exists = False
            return

        self.connect()
        instance = self._get_instance_by_id(self.vm_id, allow_missing=True)
        old_state = self.state
        #self.log("instance state is ‘{0}’".format(instance.state if instance else "gone"))

        if instance is None or instance.state in {"shutting-down", "terminated"}:
            self.state = self.MISSING
            return

        res.exists = True
        if instance.state == "pending":
            res.is_up = False
            self.state = self.STARTING

        elif instance.state == "running":
            res.is_up = True

            res.disks_ok = True
            for k, v in self.block_device_mapping.items():
                if k not in instance.block_device_mapping.keys() and v.get('volumeId', None):
                    res.disks_ok = False
                    res.messages.append("volume ‘{0}’ not attached to ‘{1}’".format(v['volumeId'], _sd_to_xvd(k)))
                    volume = nixops.ec2_utils.get_volume_by_id(self.connect(), v['volumeId'], allow_missing=True)
                    if not volume:
                        res.messages.append("volume ‘{0}’ no longer exists".format(v['volumeId']))

                if k in instance.block_device_mapping.keys() and instance.block_device_mapping[k].status != 'attached' :
                    res.disks_ok = False
                    res.messages.append("volume ‘{0}’ on device ‘{1}’ has unexpected state: ‘{2}’".format(v['volumeId'], _sd_to_xvd(k), instance.block_device_mapping[k].status))


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
        instance = self._get_instance_by_id(self.vm_id)
        instance.reboot()
        self.state = self.STARTING


    def get_console_output(self):
        if not self.vm_id:
            raise Exception("cannot get console output of non-existant machine ‘{0}’".format(self.name))
        self.connect()
        return self._conn.get_console_output(self.vm_id).output or "(not available)"


def _xvd_to_sd(dev):
    return dev.replace("/dev/xvd", "/dev/sd")


def _sd_to_xvd(dev):
    return dev.replace("/dev/sd", "/dev/xvd")
