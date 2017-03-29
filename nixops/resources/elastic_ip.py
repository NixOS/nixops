# -*- coding: utf-8 -*-

# Automatic provisioning of EC2 elastic IP addresses.

import time
import boto.ec2
import nixops.util
import nixops.resources
import nixops.ec2_utils


class ElasticIPDefinition(nixops.resources.ResourceDefinition):
    """Definition of an EC2 elastic IP address."""

    @classmethod
    def get_type(cls):
        return "elastic-ip"

    @classmethod
    def get_resource_type(cls):
        return "elasticIPs"

    def __init__(self, xml):
        nixops.resources.ResourceDefinition.__init__(self, xml)
        self.region = xml.find("attrs/attr[@name='region']/string").get("value")
        self.access_key_id = xml.find("attrs/attr[@name='accessKeyId']/string").get("value")

    def show_type(self):
        return "{0} [{1}]".format(self.get_type(), self.region)


class ElasticIPState(nixops.resources.ResourceState):
    """State of an EC2 elastic IP address."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("ec2.region", None)
    public_ipv4 = nixops.util.attr_property("ec2.ipv4", None)


    @classmethod
    def get_type(cls):
        return "elastic-ip"


    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None


    def show_type(self):
        s = super(ElasticIPState, self).show_type()
        if self.state == self.UP: s = "{0} [{1}]".format(s, self.region)
        return s


    @property
    def resource_id(self):
        return self.public_ipv4


    def connect(self, region):
        if self._conn: return
        self._conn = nixops.ec2_utils.connect(region, self.access_key_id)


    def create(self, defn, check, allow_reboot, allow_recreate):

        self.access_key_id = defn.access_key_id or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set ‘accessKeyId’, $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        if self.state == self.UP and (self.region != defn.region):
            raise Exception("changing the region of an elastic IP address is not supported")

        if self.state != self.UP:

            self.connect(defn.region)

            self.log("creating elastic IP address (region ‘{0}’)...".format(defn.region))
            address = self._conn.allocate_address()

            # FIXME: if we crash before the next step, we forget the
            # address we just created.  Doesn't seem to be anything we
            # can do about this.

            with self.depl._state.db:
                self.state = self.UP
                self.region = defn.region
                self.public_ipv4 = address.public_ip

            self.log("IP address is {0}".format(self.public_ipv4))


    def destroy(self, wipe=False):
        if self.state == self.UP:
            self.connect(self.region)
            try:
                res = self._conn.get_all_addresses(addresses=[self.public_ipv4])
                assert len(res) <= 1
                if len(res) == 1:
                    self.log("releasing elastic IP address {0}...".format(self.public_ipv4))
                    res[0].delete()
            except boto.exception.EC2ResponseError as e:
                if e.error_code != "InvalidAddress.NotFound":
                    raise
        return True
