# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC subnets.

import boto3
import botocore
import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils

class VPCSubnetDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC subnet."""

    @classmethod
    def get_type(cls):
        return "vpc-subnet"

    @classmethod
    def get_resource_type(cls):
        return "vpcSubnets"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCSubnetState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of a VPC subnet."""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    subnet_id = nixops.util.attr_property("ec2.vpc.SubnetId", None)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)
    region = nixops.util.attr_property("region", None)
    vpc_id = nixops.util.attr_property("ec2.vpc.subnetVpcId", None)
    cidr_block = nixops.util.attr_property("ec2.vpc.subnetCidrBlock", None)
    zone = nixops.util.attr_property("ec2.vpc.subnetAZ", None)
    map_public_ip_on_launch = nixops.util.attr_property("ec2.vpc.mapPublicIpOnLaunch", None)

    @classmethod
    def get_type(cls):
        return "vpc-subnet"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None

    def show_type(self):
        s = super(VPCSubnetState, self).show_type()
        if self.zone: s = "{0} [{1}]".format(s, self.zone)
        return s

    @property
    def resource_id(self):
        return self.subnet_id

    def prefix_definition(self, attr):
        return {('resources', 'vpcSubnets'): attr}

    def get_physical_spec(self):
        return {}

    def get_definition_prefix(self):
        return "resources.vpcSubnets."

    def connect(self):
        if self._client: return
        assert self.region
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.client('ec2', region_name=self.region, aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self.region = defn.config['region']

        self.connect()

        subnet_id = self.subnet_id
        zone = self.zone

        vpc_id = defn.config['vpcId']

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:], "vpc")
            vpc_id = res.vpc_id

        if self.state != self.UP:
            zone = defn.config['zone'] if defn.config['zone'] else ''
            self.log("creating subnet in vpc {0}".format(vpc_id))
            response = self._client.create_subnet(VpcId=vpc_id, CidrBlock=defn.config['cidrBlock']
                    , AvailabilityZone=zone)
            subnet = response.get('Subnet')
            subnet_id = subnet.get('SubnetId')
            zone = subnet.get('AvailabilityZone')

        self._client.modify_subnet_attribute(MapPublicIpOnLaunch={ 'Value': defn.config['mapPublicIpOnLaunch'] },
                SubnetId=subnet_id)

        def tag_updater(tags):
            self._client.create_tags(Resources=[ subnet_id ], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

        self.update_tags_using(tag_updater, user_tags=defn.config["tags"], check=check)

        with self.depl._db:
            self.state = self.UP
            self.subnet_id = subnet_id
            self.region = defn.config['region']
            self.vpc_id = vpc_id
            self.cidr_block = defn.config['cidrBlock']
            self.zone = zone
            self.map_public_ip_on_launch = defn.config['mapPublicIpOnLaunch']

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting subnet {0}".format(self.subnet_id))
        self.connect()
        self._client.delete_subnet(SubnetId=self.subnet_id)
        with self.depl._db:
            self.state = self.MISSING
            self.subnet_id = None
            self.region
            self.vpc_id = None
            self.cidr_block = None
            self.zone = None
            self.map_public_ip_on_launch = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
