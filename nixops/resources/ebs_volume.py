# -*- coding: utf-8 -*-

# Automatic provisioning of AWS EBS volumes.

import time
import boto.ec2
import nixops.util
import nixops.ec2_utils
import nixops.resources
import botocore.exceptions
import nixops.resources.ec2_common


class EBSVolumeDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EBS volume."""

    @classmethod
    def get_type(cls):
        return "ebs-volume"

    @classmethod
    def get_resource_type(cls):
        return "ebsVolumes"

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class EBSVolumeState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of an EBS volume."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    zone = nixops.util.attr_property("ec2.zone", None)
    volume_id = nixops.util.attr_property("ec2.volumeId", None)
    size = nixops.util.attr_property("ec2.size", None, int)
    iops = nixops.util.attr_property("ec2.iops", None, int)
    volume_type = nixops.util.attr_property("ec2.volumeType", None)


    @classmethod
    def get_type(cls):
        return "ebs-volume"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None
        self._conn_boto3 = None


    def _exists(self):
        return self.state != self.MISSING


    def show_type(self):
        s = super(EBSVolumeState, self).show_type()
        if self._exists(): s = "{0} [{1}]".format(s, self.zone)
        return s


    @property
    def resource_id(self):
        return self.volume_id


    def connect(self, region):
        if self._conn: return self._conn
        self._conn = nixops.ec2_utils.connect(region, self.access_key_id)
        return self._conn

    def connect_boto3(self, region):
        if self._conn_boto3: return self._conn_boto3
        self._conn_boto3 = nixops.ec2_utils.connect_ec2_boto3(region, self.access_key_id)
        return self._conn_boto3

    def _get_vol(self, config):
        self.connect_boto3(config['region'])
        try:
            _vol = self._conn_boto3.describe_volumes(
                    VolumeIds=[config['volumeId']]
                   )['Volumes'][0]
        except botocore.exceptions.ClientError as error:
            raise error
        if _vol['VolumeType'] == "io1":
            iops = _vol['Iops']
        else:
            iops = config['iops']
        with self.depl._db:
            self.state = self.STARTING
            self.region = config['region']
            self.zone = _vol['AvailabilityZone']
            self.size = _vol['Size']
            self.volume_id = config['volumeId']
            self.iops = iops
            self.volume_type = _vol['VolumeType']

    def create(self, defn, check, allow_reboot, allow_recreate):

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self.connect(defn.config['region'])

        if self._exists():
            if self.region != defn.config['region'] or self.zone != defn.config['zone']:
                raise Exception("changing the region or availability zone of an EBS volume is not supported")

            if defn.config['size'] != 0 and self.size != defn.config['size']:
                raise Exception("changing the size an EBS volume is currently not supported")

            if self.volume_type != None and defn.config['volumeType'] != self.volume_type:
                raise Exception("changing the type of an EBS volume is currently not supported")

            if defn.config['iops'] != self.iops:
                raise Exception("changing the IOPS of an EBS volume is currently not supported")

        if self.state == self.MISSING:
            if defn.config['volumeId']:
                self.log("Using provided EBS volume ‘{0}’...".format(defn.config['volumeId']))
                self._get_vol(defn.config)
            else:
                if defn.config['size'] == 0 and defn.config['snapshot'] != "":
                    snapshots = self._conn.get_all_snapshots(snapshot_ids=[defn.config['snapshot']])
                    assert len(snapshots) == 1
                    defn.config['size'] = snapshots[0].volume_size

                if defn.config['snapshot']:
                    self.log("creating EBS volume of {0} GiB from snapshot ‘{1}’...".format(defn.config['size'], defn.config['snapshot']))
                else:
                    self.log("creating EBS volume of {0} GiB...".format(defn.config['size']))

                if defn.config['zone'] is None:
                    raise Exception("please set a zone where the volume will be created")

                volume = self._conn.create_volume(
                    zone=defn.config['zone'], size=defn.config['size'], snapshot=defn.config['snapshot'],
                    iops=defn.config['iops'], volume_type=defn.config['volumeType'])
                # FIXME: if we crash before the next step, we forget the
                # volume we just created.  Doesn't seem to be anything we
                # can do about this.

                with self.depl._db:
                    self.state = self.STARTING
                    self.region = defn.config['region']
                    self.zone = defn.config['zone']
                    self.size = defn.config['size']
                    self.volume_id = volume.id
                    self.iops = defn.config['iops']
                    self.volume_type = defn.config['volumeType']

                self.log("volume ID is ‘{0}’".format(self.volume_id))

        if self.state == self.STARTING or check:
            self.update_tags(self.volume_id, user_tags=defn.config['tags'], check=check)
            nixops.ec2_utils.wait_for_volume_available(
                self._conn, self.volume_id, self.logger,
                states=['available', 'in-use'])
            self.state = self.UP

    def check(self):
        volume = nixops.ec2_utils.get_volume_by_id(self.connect(self.region), self.volume_id)
        if volume is None:
            self.state = self.MISSING

    def destroy(self, wipe=False):
        if not self._exists(): return True

        if wipe:
            log.warn("wipe is not supported")

        self.connect(self.region)
        volume = nixops.ec2_utils.get_volume_by_id(self._conn, self.volume_id, allow_missing=True)
        if not volume: return True
        if not self.depl.logger.confirm("are you sure you want to destroy EBS volume ‘{0}’?".format(self.name)): return False
        self.log("destroying EBS volume ‘{0}’...".format(self.volume_id))
        volume.delete()
        return True
