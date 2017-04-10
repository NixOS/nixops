# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPCs.

import boto
import boto.vpc
import nixops.util
import nixops.resources
import nixops.ec2_utils

class VPCDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC."""

    @classmethod
    def get_type(cls):
        return "vpc"

    @classmethod
    def get_resource_type(cls):
        return "vpc"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCState(nixops.resources.ResourceState):
    """State of a VPC."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    vpcId = nixops.util.attr_property("ec2.vpcId",None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("region", None)

    @classmethod
    def get_type(cls):
        return "vpc"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._conn = None

    def show_type(self):
        s = super(VPCState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self.vpcId

    def prefix_definition(self, attr):
        return {('resources', 'vpc'): attr}

    def get_physical_spec(self):
        return {}

    def get_definition_prefix(self):
        return "resources.vpc."

    def connect(self):
        if self._conn: return
        assert self.region
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._conn = boto.vpc.connect_to_region(
            region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def _destroy(self):
        self.state = self.MISSING
        print "TODO destroy"

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self.region = defn.config['region']
        instance_tenancy = True if defn.config['instanceTenancy'] == 'true' else False
        enable_dns_support = True if defn.config['enableDnsSupport'] == 'true' else False
        enable_dns_hostnames

        if self.state != self.UP:
            self.connect()
            self.log("creating vpc")
            vpc = self._conn.create_vpc(cidr_block=defn.config['cidrBlock'], instance_tenancy=instance_tenancy)
            print vpc
            print vpc.id

        with self.depl._db:
           self.state = self.UP
           self.vpc_id = vpc.id
           self.region = defn.config['region']
           self.cidr_block = defn.config['cidrBlock'] 
           self.instance_tenancy = instance_tenancy
           self.classic_link_enabled = classic_link_enabled
           self.enable_dns_support = enable_dns_support
           self.enable_dns_hostnames = enable_dns_hostnames

    def destroy(self, wipe=False):
        self._destroy()
        return True
