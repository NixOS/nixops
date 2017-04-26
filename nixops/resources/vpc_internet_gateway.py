# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC internet gateways.

import os

import boto3
import botocore

from nixops.state import StateDict
from nixops.diff import Diff
import nixops.util
import nixops.resources
import nixops.resources.ec2_common
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


class VPCInternetGatewayState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of a VPC internet gateway."""
    # keeping the old state attribute so that we don't break nixops
    # behavior e.g nixops info
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("ec2.accessKeyId", None)

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self._client = None

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
        self._client = boto3.client('ec2', region_name=self._state['region'], aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        if os.environ.get('NIXOPS_PLAN'):
            diff = Diff(depl=self.depl, enable_handler=True, logger=self.logger,
                    config=defn.config, state=self._state, res_type=self.get_type())
            diff.set_reserved_keys(['internetGatewayId', 'ec2.accessKeyId'])
            diff.plan()
            return

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self._state['region'] = defn.config['region']

        self.connect()

        vpc_id = defn.config['vpcId']
        igw_id = self._state.get('internetGatewayId', None)

        if self.state != self.UP:
            self.log("creating internet gateway")
            response = self._client.create_internet_gateway()
            igw_id = response['InternetGateway']['InternetGatewayId']
            self.log("attaching internet gateway {0} to vpc {1}".format(igw_id, vpc_id))
            self._client.attach_internet_gateway(InternetGatewayId=igw_id,
                    VpcId=vpc_id)

        with self.depl._db:
            self.state = self.UP
            self._state['region'] = defn.config['region']
            self._state['vpcId'] = vpc_id
            self._state['internetGatewayId'] = igw_id

    def _destroy(self):
        if self.state != self.UP: return
        self.log("detaching internet gateway {0} from vpc {1}".format(self._state['internetGatewayId'],
            self._state['vpcId']))
        self.connect()
        self._client.detach_internet_gateway(InternetGatewayId=self._state['internetGatewayId'],
                VpcId=self._state['vpcId'])
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
