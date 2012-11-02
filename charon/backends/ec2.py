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
from charon.backends import MachineDefinition, MachineState
import charon.known_hosts
import charon.util
from xml import etree


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
        if self.ami == "": raise Exception("no AMI defined for EC2 machine ‘{0}’".format(self.name))
        self.instance_type = x.find("attr[@name='instanceType']/string").get("value")
        self.key_pair = x.find("attr[@name='keyPair']/string").get("value")
        self.private_key = x.find("attr[@name='privateKey']/string").get("value")
        self.security_groups = [e.get("value") for e in x.findall("attr[@name='securityGroups']/list/string")]
        self.instance_profile = x.find("attr[@name='instanceProfile']/string").get("value")
        self.tags = {k.get("name"): k.find("string").get("value") for k in x.findall("attr[@name='tags']/attrs/attr")}
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


class EC2State(MachineState):
    """State of an EC2 machine."""

    @classmethod
    def get_type(cls):
        return "ec2"

    state = charon.util.attr_property("state", MachineState.MISSING, int) # override
    public_ipv4 = charon.util.attr_property("publicIpv4", None)
    private_ipv4 = charon.util.attr_property("privateIpv4", None)
    elastic_ipv4 = charon.util.attr_property("ec2.elasticIpv4", None)
    access_key_id = charon.util.attr_property("ec2.accessKeyId", None)
    region = charon.util.attr_property("ec2.region", None)
    zone = charon.util.attr_property("ec2.zone", None)
    controller = charon.util.attr_property("ec2.controller", None) # FIXME: not used
    ami = charon.util.attr_property("ec2.ami", None)
    instance_type = charon.util.attr_property("ec2.instanceType", None)
    key_pair = charon.util.attr_property("ec2.keyPair", None)
    public_host_key = charon.util.attr_property("ec2.publicHostKey", None)
    private_key_file = charon.util.attr_property("ec2.privateKeyFile", None)
    instance_profile = charon.util.attr_property("ec2.instanceProfile", None)
    security_groups = charon.util.attr_property("ec2.securityGroups", None, 'json')
    tags = charon.util.attr_property("ec2.tags", {}, 'json')
    block_device_mapping = charon.util.attr_property("ec2.blockDeviceMapping", {}, 'json')
    root_device_type = charon.util.attr_property("ec2.rootDeviceType", None)
    backups = charon.util.attr_property("ec2.backups", {}, 'json')
    dns_hostname = charon.util.attr_property("route53.hostName", None)
    dns_ttl = charon.util.attr_property("route53.ttl", None, int)
    route53_access_key_id = charon.util.attr_property("route53.accessKeyId", None)

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


    def get_ssh_flags(self):
        return ["-i", self.private_key_file] if self.private_key_file else []


    def get_physical_spec(self, machines):
        lines = ['    require = [ <nixos/modules/virtualisation/amazon-config.nix> ];']

        for k, v in self.block_device_mapping.items():
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") != "":
                lines.append('    deployment.ec2.blockDeviceMapping."{0}".passphrase = pkgs.lib.mkOverride 10 "{1}";'
                             .format(_sd_to_xvd(k), v['generatedKey']))

        return lines


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
        s = MachineState.show_type(self)
        if self.zone or self.region: s = "{0} [{1}; {2}]".format(s, self.zone or self.region, self.instance_type)
        return s


    def address_to(self, m):
        if isinstance(m, EC2State):
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


    def fetch_aws_secret_key(self, access_key_id):
        secret_access_key = os.environ.get('EC2_SECRET_KEY') or os.environ.get('AWS_SECRET_ACCESS_KEY')
        path = os.path.expanduser("~/.ec2-keys")
        if os.path.isfile(path):
            f = open(path, 'r')
            contents = f.read()
            f.close()
            for l in contents.splitlines():
                l = l.split("#")[0] # drop comments
                w = l.split()
                if len(w) < 2 or len(w) > 3: continue
                if len(w) == 3 and w[2] == access_key_id:
                    access_key_id = w[0]
                    secret_access_key = w[1]
                    break
                if w[0] == access_key_id:
                    secret_access_key = w[1]
                    break

        if not secret_access_key:
            raise Exception("please set $EC2_SECRET_KEY or $AWS_SECRET_ACCESS_KEY, or add the key for ‘{0}’ to ~/.ec2-keys"
                            .format(access_key_id))

        return (access_key_id, secret_access_key)


    def connect(self):
        if self._conn: return
        assert self.region

        # Get the secret access key from the environment or from ~/.ec2-keys.
        (access_key_id, secret_access_key) = self.fetch_aws_secret_key(self.access_key_id)

        self._conn = boto.ec2.connect_to_region(
            region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)


    def connect_route53(self):
        if self._conn_route53: return

        # Get the secret access key from the environment or from ~/.ec2-keys.
        (access_key_id, secret_access_key) = self.fetch_aws_secret_key(self.route53_access_key_id)

        self._conn_route53 = boto.connect_route53(access_key_id, secret_access_key)


    def _get_instance_by_id(self, instance_id, allow_missing=False):
        """Get instance object by instance id."""
        self.connect()
        reservations = self._conn.get_all_instances([instance_id])
        if len(reservations) == 0:
            if allow_missing: return None
            raise Exception("EC2 instance ‘{0}’ disappeared!".format(instance_id))
        return reservations[0].instances[0]


    def _get_volume_by_id(self, volume_id):
        """Get instance object by instance id."""
        self.connect()
        volumes = self._conn.get_all_volumes([volume_id])
        if len(volumes) != 1:
            raise Exception("unable to find volume ‘{0}’".format(volume_id))
        return volumes[0]


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
            self.log_continue("({0}) ".format(instance.state))
            if instance.state not in {"pending", "running", "scheduling", "launching", "stopped"}:
                raise Exception("EC2 instance ‘{0}’ failed to start (state is ‘{1}’)".format(self.vm_id, instance.state))
            if instance.ip_address: break
            time.sleep(3)

        self.log_end("{0} / {1}".format(instance.ip_address, instance.private_ip_address))

        charon.known_hosts.add(instance.ip_address, self.public_host_key)

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
                    backup_complete = False
                    info.append("{0} - {1} - Not available in backup".format(self.name, k))
                else:
                    snapshot_id = b[k]
                    try:
                        snapshot = self._get_snapshot_by_id(snapshot_id)
                        snapshot_status = snapshot.update()
                        if snapshot_status != '100%':
                            info.append("progress[{0},{1},{2}] = {3}%.".format(self.name, k, snapshot_id, snapshot_status))
                            backup_status = "running"
                    except:
                        info.append("{0} - {1} - {2} - Snapshot has disappeared".format(self.name, k, snapshot_id))
                        backup_status = "unavailable"
                backups[b_id]['status'] = backup_status
                backups[b_id]['info'] = info
        return backups


    def backup(self, backup_id):
        self.connect()

        self.log("backing up machine ‘{0}’ using id ‘{1}’".format(self.name, backup_id))
        backup = {}
        _backups = self.backups
        for k, v in self.block_device_mapping.items():
            snapshot = self._conn.create_snapshot(volume_id=v['volumeId'])
            self.log("+ created snapshot of volume ‘{0}’: ‘{1}’".format(v['volumeId'], snapshot.id))

            common_tags = {'CharonNetworkUUID': str(self.depl.uuid), 'CharonMachineName': self.name, 'CharonBackupID': backup_id, 'CharonBackupDevice': k}
            snapshot_tags = {'Name': "{0} - {3} [{1} - {2}]".format(self.depl.description, self.name, k, backup_id)}
            snapshot_tags.update(common_tags)
            self._conn.create_tags([snapshot.id], snapshot_tags)
            backup[k] = snapshot.id
        _backups[backup_id] = backup
        self.backups = _backups

    def restore(self, defn, backup_id):
        self.stop()

        self.log("restoring machine ‘{0}’ to backup ‘{1}’".format(self.name, backup_id))

        for k, v in self.block_device_mapping.items():
            # detach disks
            volume = self._get_volume_by_id(v['volumeId'])
            if volume.update() == "in-use":
                self.log("detaching volume from ‘{0}’".format(self.name))
                volume.detach()

            # attach backup disks
            snapshot_id = self.backups[backup_id][k]
            self.log("creating volume from snapshot ‘{0}’".format(snapshot_id))
            new_volume = self._conn.create_volume(size=0, snapshot=snapshot_id, zone=self.zone)

            # wait for available
            while True:
                sys.stderr.write("[{0}] ".format(volume.status))
                if volume.status == "available": break
                time.sleep(3)
                volume.update()
            sys.stderr.write("\n")

            self.log("attaching volume ‘{0}’ to ‘{1}’".format(new_volume.id, self.name))
            new_volume.attach(self.vm_id, k)
            self.block_device_mapping[k]['volumeId'] = new_volume.id # FIXME


    def create(self, defn, check, allow_reboot):
        assert isinstance(defn, EC2Definition)
        assert defn.type == "ec2"

        if self.state != self.UP: check = True

        self.set_common_state(defn)

        # Figure out the access key.
        self.access_key_id = defn.access_key_id or os.environ.get('EC2_ACCESS_KEY') or os.environ.get('AWS_ACCESS_KEY_ID')
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

        # Create the instance.
        if not self.vm_id:
            self.log("creating EC2 instance (AMI ‘{0}’, type ‘{1}’, region ‘{2}’)...".format(
                defn.ami, defn.instance_type, defn.region))
            self._reset_state()

            self.region = defn.region
            self.connect()

            # Figure out whether this AMI is EBS-backed.
            ami = self._conn.get_all_images([defn.ami])[0]

            self.root_device_type = ami.root_device_type

            (private, public) = self._create_key_pair()

            user_data = "SSH_HOST_DSA_KEY_PUB:{0}\nSSH_HOST_DSA_KEY:{1}\n".format(public, private.replace("\n", "|"))

            zone = defn.zone or None

            devmap = boto.ec2.blockdevicemapping.BlockDeviceMapping()
            devs_mapped = {}
            ebs_optimized = False
            for k, v in defn.block_device_mapping.iteritems():
                (volume_type, iops) = self.disk_volume_options(v)
                if volume_type != "standard":
                    ebs_optimized = True

                if re.match("/dev/sd[a-e]", k) and not v['disk'].startswith("ephemeral"):
                    raise Exception("non-ephemeral disk not allowed on device ‘{0}’; use /dev/xvdf or higher".format(_sd_to_xvd(k)))
                if v['disk'] == '':
                    if self._booted_from_ebs():
                        devmap[k] = boto.ec2.blockdevicemapping.BlockDeviceType(
                            size=v['size'], delete_on_termination=v['deleteOnTermination'], volume_type=volume_type, iops=iops)
                        self.update_block_device_mapping(k, v)
                    # Otherwise, it's instance store backed, and we'll create the volume later.
                elif v['disk'].startswith("ephemeral"):
                    devmap[k] = boto.ec2.blockdevicemapping.BlockDeviceType(ephemeral_name=v['disk'])
                    self.update_block_device_mapping(k, v)
                elif v['disk'].startswith("snap-"):
                    devmap[k] = boto.ec2.blockdevicemapping.BlockDeviceType(snapshot_id=v['disk'], delete_on_termination=True, volume_type=volume_type, iops=iops)
                    self.update_block_device_mapping(k, v)
                elif v['disk'].startswith("vol-"):
                    # Volumes cannot be attached at boot time, so
                    # attach it later.  But make note of the placement
                    # zone of the volume.
                    volume = self._get_volume_by_id(v['disk'])
                    if not zone:
                        self.log("starting EC2 instance in zone ‘{0}’ due to volume ‘{1}’".format(
                            volume.zone, v['disk']))
                        zone = volume.zone
                    elif zone != volume.zone:
                        raise Exception("unable to start EC2 instance ‘{0}’ in zone ‘{1}’ because volume ‘{2}’ is in zone ‘{3}’"
                                        .format(self.name, zone, v['disk'], volume.zone))
                else:
                    raise Exception("device mapping ‘{0}’ not (yet) supported".format(v['disk']))

            # FIXME: Should use client_token to ensure idempotency.
            reservation = self._conn.run_instances(
                instance_type=defn.instance_type,
                placement=zone,
                key_name=defn.key_pair,
                security_groups=defn.security_groups,
                block_device_map=devmap,
                user_data=user_data,
                image_id=defn.ami,
                instance_profile_name=defn.instance_profile,
                ebs_optimized=ebs_optimized)

            assert len(reservation.instances) == 1

            instance = reservation.instances[0]

            with self.depl._db:
                self.state = self.STARTING
                self.vm_id = instance.id
                self.controller = defn.controller
                self.ami = defn.ami
                self.instance_type = defn.instance_type
                self.key_pair = defn.key_pair
                self.security_groups = defn.security_groups
                self.zone = instance.placement
                self.public_host_key = public

        # There is a short time window during which EC2 doesn't
        # know the instance ID yet.  So wait until it does.
        while True:
            try:
                instance = self._get_instance_by_id(self.vm_id)
                break
            except boto.exception.EC2ResponseError as e:
                if e.error_code != "InvalidInstanceID.NotFound": raise
            self.log("EC2 instance ‘{0}’ not known yet, waiting...".format(self.vm_id))
            time.sleep(3)

        # Warn about some EC2 options that we cannot update for an existing instance.
        if self.instance_type != defn.instance_type:
            self.warn("cannot change type of a running instance (use ‘--allow-reboot’)")
        if self.region != defn.region:
            self.warn("cannot change region of a running instance")
        if defn.zone and self.zone != defn.zone:
            self.warn("cannot change availability zone of a running instance")

        # Reapply tags if they have changed.
        common_tags = {'CharonNetworkUUID': self.depl.uuid,
                       'CharonMachineName': self.name,
                       'CharonStateFile': "{0}@{1}:{2}".format(getpass.getuser(), socket.gethostname(), self.depl._db.db_file)}

        if self.owners != []:
            common_tags['Owners'] = ", ".join(self.owners)

        tags = {'Name': "{0} [{1}]".format(self.depl.description, self.name)}
        tags.update(defn.tags)
        tags.update(common_tags)
        if check or self.tags != tags:
            self.connect()
            self._conn.create_tags([self.vm_id], tags)
            # TODO: remove obsolete tags?
            self.tags = tags

        # Assign or release an elastic IP address, if given.
        if (self.elastic_ipv4 or "") != defn.elastic_ipv4 or check:
            self.connect()

            if defn.elastic_ipv4 != "":
                # wait until machine is in running state
                self.log_start("waiting for machine to be in running state... ".format(self.name))
                while True:
                    self.log_continue("({0}) ".format(instance.state))
                    if instance.state == "running": break
                    if instance.state not in {"running", "pending"}:
                        raise Exception(
                            "EC2 instance ‘{0}’ failed to reach running state (state is ‘{1}’)"
                            .format(self.vm_id, instance.state))
                    time.sleep(3)
                    instance.update()
                self.log_end("")

                addresses = self._conn.get_all_addresses(addresses=[defn.elastic_ipv4])
                if addresses[0].instance_id != "" \
                   and addresses[0].instance_id != self.vm_id \
                   and not self.depl.confirm("are you sure you want to associate IP address ‘{0}’, which is currently in use by instance ‘{1}’?".format(defn.elastic_ipv4, addresses[0].instance_id)):
                    raise Exception("elastic IP ‘{0}’ already in use...".format(defn.elastic_ipv4))
                else:
                    self.log("associating IP address ‘{0}’...".format(defn.elastic_ipv4))
                    addresses[0].associate(self.vm_id)
                    self.log_start("waiting for address to be associated with this machine...")
                    instance.update()
                    while True:
                        self.log_continue("({0}) ".format(instance.ip_address))
                        if instance.ip_address == defn.elastic_ipv4: break
                        time.sleep(3)
                        instance.update()
                    self.log_end("")

                charon.known_hosts.add(defn.elastic_ipv4, self.public_host_key)
                with self.depl._db:
                    self.elastic_ipv4 = defn.elastic_ipv4
                    self.public_ipv4 = defn.elastic_ipv4
                    self.ssh_pinged = False

            elif self.elastic_ipv4 != None:
                self.log("disassociating IP address ‘{0}’...".format(self.elastic_ipv4))
                self._conn.disassociate_address(public_ip=self.elastic_ipv4)
                with self.depl._db:
                    self.elastic_ipv4 = None
                    self.public_ipv4 = None
                    self.ssh_pinged = False

        # Wait for the IP address.
        if not self.public_ipv4 or check:
            instance = self._get_instance_by_id(self.vm_id)
            self._wait_for_ip(instance)

        if defn.dns_hostname:
            self._update_route53(defn)

        # Wait until the instance is reachable via SSH.
        self.wait_for_ssh(check=check)

        # Create missing volumes.
        # FIXME: support snapshots.
        for k, v in defn.block_device_mapping.iteritems():
            if k not in self.block_device_mapping and v['disk'] == '':
                self.log("creating {0} GiB volume...".format(v['size']))
                self.connect()
                (volume_type, iops) = self.disk_volume_options(v)
                volume = self._conn.create_volume(size=v['size'], zone=self.zone, volume_type=volume_type, iops=iops)
                # The flag charonDeleteOnTermination denotes that on
                # instance termination, we have to delete the volume
                # ourselves.  For volumes created at instance creation
                # time, EC2 will do it for us.
                v['charonDeleteOnTermination'] = v['deleteOnTermination']
                v['needsAttach'] = True
                v['volumeId'] = volume.id
                self.update_block_device_mapping(k, v)

        # Attach missing volumes.
        for k, v in defn.block_device_mapping.iteritems():
            if k not in self.block_device_mapping:
                self.log("attaching volume ‘{0}’ as ‘{1}’...".format(v['disk'], _sd_to_xvd(k)))
                self.connect()
                if v['disk'].startswith("vol-"):
                    self._conn.attach_volume(v['disk'], self.vm_id, k)
                    self.update_block_device_mapping(k, v)
                if v['disk'].startswith("snap-"):
                    (volume_type, iops) = self.disk_volume_options(v)
                    new_volume = self._conn.create_volume(size=0, snapshot=v['disk'], zone=self.zone, volume_type=volume_type, iops=iops)
                    new_volume.attach(self.vm_id, k)
                    v['disk'] = new_volume.id
                    self.update_block_device_mapping(k, v)
                else:
                    raise Exception("adding device mapping ‘{0}’ to a running instance is not (yet) supported".format(v['disk']))

        for k, v in self.block_device_mapping.items():
            if v.get('needsAttach', False):
                self.log("attaching volume ‘{0}’ as ‘{1}’...".format(v['volumeId'], _sd_to_xvd(k)))
                self.connect()

                volume_tags = {'Name': "{0} [{1} - {2}]".format(self.depl.description, self.name, _sd_to_xvd(k))}
                volume_tags.update(common_tags)
                self._conn.create_tags([v['volumeId']], volume_tags)

                volume = self._get_volume_by_id(v['volumeId'])
                if volume.volume_state() == "available":
                    self._conn.attach_volume(v['volumeId'], self.vm_id, k)
                # Wait until the device is visible in the instance.
                def check_dev():
                    res = self.run_command("test -e {0}".format(_sd_to_xvd(k)), check=False)
                    return res == 0
                charon.util.check_wait(check_dev)
                del v['needsAttach']
                self.update_block_device_mapping(k, v)

        # Add disks that were in the original device mapping of image.
        for k, dm in instance.block_device_mapping.items():
            if k not in self.block_device_mapping:
                if dm.volume_id:
                    bdm = {}
                    bdm['volumeId'] = dm.volume_id
                    bdm['partOfImage'] = True
                    self.update_block_device_mapping(k, bdm)

        # FIXME: process changes to the deleteOnTermination flag.

        # Get the volume IDs of automatically created volumes (because
        # it's good to have these in the state file).
        for k, v in self.block_device_mapping.items():
            if not 'volumeId' in v:
                self.connect()
                volumes = self._conn.get_all_volumes(
                    filters={'attachment.instance-id': self.vm_id,
                             'attachment.device': k})
                if len(volumes) != 1:
                    raise Exception("unable to find volume attached to ‘{0}’ on EC2 machine ‘{1}’".format(k, self.name))
                v['volumeId'] = volumes[0].id # FIXME
                self.update_block_device_mapping(k, v)

        # Detach volumes that are no longer in the deployment spec.
        for k, v in self.block_device_mapping.items():
            if k not in defn.block_device_mapping and not v.get('partOfImage', False):
                self.log("detaching device ‘{0}’...".format(_sd_to_xvd(k)))
                self.connect()
                volumes = self._conn.get_all_volumes([], filters={'attachment.instance-id': self.vm_id, 'attachment.device': k})
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

        # Auto-generate LUKS keys if the model didn't specify one.
        for k, v in self.block_device_mapping.items():
            if v.get('encrypt', False) and v.get('passphrase', "") == "" and v.get('generatedKey', "") == "":
                v['generatedKey'] = charon.util.generate_random_string(length=256)
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

        zones = [zone for zone in zones['ListHostedZonesResponse']['HostedZones'] if "{0}.".format(hosted_zone) == zone.Name]
        if len(zones) != 1:
            raise Exception('hosted zone for {0} not found'.format(hosted_zone))
        zoneid = zones[0]['Id'].split("/")[2]

        prevrrs = self._conn_route53.get_all_rrsets(hosted_zone_id=zoneid, type="A", name="{0}.".format(self.dns_hostname))
        changes = boto.route53.record.ResourceRecordSets(connection=self._conn_route53, hosted_zone_id=zoneid)
        if len(prevrrs) > 0:
            for prevrr in prevrrs:
                change = changes.add_change("DELETE", self.dns_hostname, "A")
                change.add_value(",".join(prevrr.resource_records))

        change = changes.add_change("CREATE", self.dns_hostname, "A")
        change.add_value(self.public_ipv4)
        changes.commit()


    def _delete_volume(self, volume_id):
        if not self.depl.confirm("are you sure you want to destroy EC2 volume ‘{0}’?".format(volume_id)):
            raise Exception("not destroying EC2 volume ‘{0}’".format(volume_id))
        self.log("destroying EC2 volume ‘{0}’...".format(volume_id))
        try:
            volume = self._get_volume_by_id(volume_id)
            charon.util.check_wait(lambda: volume.update() == 'available')
            volume.delete()
        except boto.exception.EC2ResponseError as e:
            # Ignore volumes that have disappeared already.
            if e.error_code != "InvalidVolume.NotFound": raise


    def destroy(self):
        if not self.vm_id: return True
        if not self.depl.confirm("are you sure you want to destroy EC2 machine ‘{0}’?".format(self.name)): return False

        self.log_start("destroying EC2 machine... ".format(self.name))

        instance = self._get_instance_by_id(self.vm_id)
        instance.terminate()

        # Wait until it's really terminated.
        while True:
            self.log_continue("({0}) ".format(instance.state))
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

        self.log_start("stopping EC2 machine... ".format(self.name))

        instance = self._get_instance_by_id(self.vm_id)
        instance.stop() # no-op if the machine is already stopped

        self.state = self.STOPPING

        # Wait until it's really stopped.
        while True:
            self.log_continue("({0}) ".format(instance.state))
            if instance.state == "stopped": break
            if instance.state not in {"running", "stopping"}:
                raise Exception(
                    "EC2 instance ‘{0}’ failed to stop (state is ‘{1}’)"
                    .format(self.vm_id, instance.state))
            time.sleep(3)
            instance.update()
        self.log_end("")

        self.state = self.STOPPED


    def start(self):
        if not self._booted_from_ebs(): return

        self.log("starting EC2 machine".format(self.name))

        instance = self._get_instance_by_id(self.vm_id)
        instance.start() # no-op if the machine is already started

        self.state = self.STARTING

        # Wait until it's really started, and obtain its new IP
        # address.  Warn the user if the IP address has changed (which
        # is generally the case).
        prev_private_ipv4 = self.private_ipv4
        prev_public_ipv4 = self.public_ipv4

        self._wait_for_ip(instance)

        if prev_private_ipv4 != self.private_ipv4 or prev_public_ipv4 != self.public_ipv4:
            self.warn("IP address has changed, you may need to run ‘charon deploy’")

        self.wait_for_ssh(check=True)


    def check(self):
        if not self.vm_id: return
        self.connect()
        instance = self._get_instance_by_id(self.vm_id, allow_missing=True)
        old_state = self.state
        self.log("instance state is ‘{0}’".format(instance.state if instance else "gone"))
        if instance is None or instance.state in {"shutting-down", "terminated"}:
            self.state = self.MISSING
        elif instance.state == "pending":
            self.state = self.STARTING
        elif instance.state == "running":
            if self.private_ipv4 != instance.private_ip_address or self.public_ipv4 != instance.ip_address:
                self.warn("IP address has changed, you may need to run ‘charon deploy’")
                self.private_ipv4 = instance.private_ip_address
                self.public_ipv4 = instance.ip_address
            MachineState.check(self)
        elif instance.state == "stopping":
            self.state = self.STOPPING
        elif instance.state == "stopped":
            self.state = self.STOPPED


    def reboot(self):
        self.log("rebooting EC2 machine... ")
        instance = self._get_instance_by_id(self.vm_id)
        instance.reboot()
        self.state = self.STARTING


def _xvd_to_sd(dev):
    return dev.replace("/dev/xvd", "/dev/sd")

def _sd_to_xvd(dev):
    return dev.replace("/dev/sd", "/dev/xvd")
