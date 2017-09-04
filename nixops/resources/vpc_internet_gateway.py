# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC internet gateways.

import os

import boto3
import botocore

from nixops.state import StateDict
from nixops.diff import Diff, Handler
import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils

class VPCInternetGatewayDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC internet gateway."""

    @classmethod
    def get_type(cls):
        return "vpc-internet-gateway"

    @classmethod
    def get_resource_type(cls):
        return "vpcInternetGateways"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCInternetGatewayState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC internet gateway."""
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["internetGatewayId"]

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self._client = None
        self.handle_create_igw = Handler(['region', 'vpcId'], handle=self.realize_create_gtw)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_igw], handle=self.realize_update_tag)

    @classmethod
    def get_type(cls):
        return "vpc-internet-gateway"

    def show_type(self):
        s = super(VPCInternetGatewayState, self).show_type()
        if self._state.get('region', None): s = "{0} [{1}]".format(s, self._state['region'])
        return s

    @property
    def resource_id(self):
        return self._state.get('internetGatewayId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcInternetGateways'): attr}

    def get_defintion_prefix(self):
        return "resources.vpcInternetGateways."

    def connect(self):
        if self._client: return
        assert self._state['region']
        (access_key_id, secret_access_key) = nixops.ec2_utils.fetch_aws_secret_key(self.access_key_id)
        self._client = boto3.session.Session().client('ec2', region_name=self._state['region'], aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

    def realize_create_gtw(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("internet gateway {} defintion changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['internetGatewayId']))
            self.warn("internet gateway changed, recreating...")
            self._destroy()
            self._client = None

        self._state['region'] = config['region']

        self.connect()

        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating internet gateway in region {}".format(self._state['region']))
        response = self._client.create_internet_gateway()
        igw_id = response['InternetGateway']['InternetGatewayId']
        self.log("attaching internet gateway {0} to vpc {1}".format(igw_id, vpc_id))
        self._client.attach_internet_gateway(InternetGatewayId=igw_id,
                                             VpcId=vpc_id)
        with self.depl._db:
            self.state = self.UP
            self._state['region'] = config['region']
            self._state['vpcId'] = vpc_id
            self._state['internetGatewayId'] = igw_id

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        self.connect()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self._client.create_tags(Resources=[self._state['internetGatewayId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != self.UP: return
        self.log("detaching internet gateway {0} from vpc {1}".format(self._state['internetGatewayId'],
            self._state['vpcId']))
        self.connect()
        self._retry(lambda: self._client.detach_internet_gateway(InternetGatewayId=self._state['internetGatewayId'],
                VpcId=self._state['vpcId']))
        self.log("deleting internet gateway {0}".format(self._state['internetGatewayId']))
        self._client.delete_internet_gateway(InternetGatewayId=self._state['internetGatewayId'])

        with self.depl._db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['vpcId'] = None
            self._state['internetGatewayId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
