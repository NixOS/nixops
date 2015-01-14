# -*- coding: utf-8 -*-

# Automatic provisioning of AWS EBS volumes.

import time
import boto.ec2
import nixops.util
import nixops.ec2_utils
import nixops.resources
import nixops.resources.ec2_common


class EBSVolumeDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EBS volume."""

    @classmethod
    def get_type(cls):
        return "ebs-volume"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        if xml.find("attrs/attr[@name='name']/null") is None:
            self.volume_name = xml.find("attrs/attr[@name='name']/string").get("value")
        else:
            self.volume_name = None
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.zone = xml.find("attrs/attr[@name='zone']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")
        self.size = int(xml.find("attrs/attr[@name='size']/int").get("value"))
        self.snapshot = xml.find("attrs/attr[@name='snapshot']/string").get("value")
        self.iops = int(xml.find("attrs/attr[@name='iops']/int").get("value"))
        if self.iops == 0: self.iops = None
        self.volume_type = xml.find("attrs/attr[@name='volumeType']/string").get("value")

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
    volume_name = nixops.util.attr_property("ec2.volumeName", None)


    @classmethod
    def get_type(cls):
        return "ebs-volume"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


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


    def create(self, defn, check, allow_reboot, allow_recreate):

        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self._exists():
            if self.region != defn.region or self.zone != defn.zone:
                raise Exception("changing the region or availability zone of an EBS volume is not supported")

            if defn.size != 0 and self.size != defn.size:
                raise Exception("changing the size an EBS volume is currently not supported")

            if self.volume_type != None and defn.volume_type != self.volume_type:
                raise Exception("changing the type of an EBS volume is currently not supported")

            if defn.iops != self.iops:
                raise Exception("changing the IOPS of an EBS volume is currently not supported")

        if self.state == self.MISSING:

            self.connect(defn.region)

            if defn.size == 0 and defn.snapshot != "":
                snapshots = self._conn.get_all_snapshots(snapshot_ids=[defn.snapshot])
                assert len(snapshots) == 1
                defn.size = snapshots[0].volume_size

            if defn.snapshot:
                self.log("creating EBS volume of {0} GiB from snapshot ‘{1}’...".format(defn.size, defn.snapshot))
            else:
                self.log("creating EBS volume of {0} GiB...".format(defn.size))

            volume = self._conn.create_volume(
                zone=defn.zone, size=defn.size, snapshot=defn.snapshot,
                iops=defn.iops, volume_type=defn.volume_type)

            # FIXME: if we crash before the next step, we forget the
            # volume we just created.  Doesn't seem to be anything we
            # can do about this.

            with self.depl._db:
                self.state = self.STARTING
                self.region = defn.region
                self.zone = defn.zone
                self.size = defn.size
                self.volume_id = volume.id
                self.iops = defn.iops
                self.volume_type = defn.volume_type

            self.log("volume ID is ‘{0}’".format(volume.id))

        volume_tags = self.get_common_tags()
        volume_tags['Name'] = defn.volume_name or "{0} [{1}]".format(self.depl.description, self.name)

        if self.state == self.STARTING or check or self.volume_name != volume_tags['Name']:
            self.connect(self.region)

            self._conn.create_tags([self.volume_id], volume_tags)
            self.volume_name = volume_tags['Name']

        if self.state == self.STARTING or check:
            self.connect(self.region)

            nixops.ec2_utils.wait_for_volume_available(
                self._conn, self.volume_id, self.logger,
                states=['available', 'in-use'])

            self.state = self.UP


    def destroy(self, wipe=False):
        if self._exists():
            self.connect(self.region)
            volume = nixops.ec2_utils.get_volume_by_id(self._conn, self.volume_id, allow_missing=True)
            if volume:
                if not self.depl.logger.confirm("are you sure you want to destroy EBS volume ‘{0}’?".format(self.name)): return False
                self.log("destroying EBS volume ‘{0}’...".format(self.volume_id))
                volume.delete()
        return True
