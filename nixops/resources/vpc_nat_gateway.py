# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC NAT gateways.

import uuid

import boto3
import botocore

import nixops.util
import nixops.resources
import nixops.resources.ec2_common
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCNatGatewayDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC NAT gateway"""

    @classmethod
    def get_type(cls):
        return "vpc-nat-gateway"

    @classmethod
    def get_resource_type(cls):
        return "vpcNatGateways"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCNatGatewayState(nixops.resources.ResourceState, nixops.resources.ec2_common.EC2CommonState):
    """State of a VPC NAT gateway"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    handle_create_gtw = Handler(['region', 'subnetId', 'allocationId'])
    _reserved_keys = ['natGatewayId', 'accessKeyId', 'tags', 'ec2.tags', 'creationToken']

    @classmethod
    def get_type(cls):
        return "vpc-nat-gateway"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self._config = None
        self.region = self._state.get('region', None)
        self.nat_gtw_id = self._state.get('natGatewayId', None)
        self.handle_create_gtw.handle = self.realize_create_gtw

    def show_type(self):
        s = super(VPCNatGatewayState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('natGatewayId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcNatGateways'): attr}

    def get_physical_spec(self):
        return { 'natGatewayId': self._state.get('natGatewayId', None) }

    def get_definition_prefix(self):
        return "resources.vpcNatGateways."

    def connect(self):
        if self._client: return
        self._client = nixops.ec2_utils.connect_ec2_boto3(self._state['region'], self.access_key_id)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        self._config = defn.config
        self.setup_diff_engine()
        change_sequence = self.diff_engine.plan()

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        self._state['region'] = self._config['region']
        self.connect()

        for h in change_sequence:
            h.handle()

    def realize_create_gtw(self):
        subnet_id = self._config['subnetId']
        allocation_id = self._config['allocationId']
        if subnet_id.startswith("res-"):
            res = self.depl.get_typed_resource(subnet_id[4:].split(".")[0], "vpc-subnet")
            subnet_id = res._state['subnetId']

        if not self._state.get('creationToken', None):
            self._state['creationToken'] = str(uuid.uuid4())
            self.state = self.STARTING

        response = self._client.create_nat_gateway(ClientToken=self._state['creationToken'], AllocationId=allocation_id,
                                                   SubnetId=subnet_id)

        gtw_id = response['NatGateway']['NatGatewayId']
        with self.depl._db:
            self.state = self.UP
            self._state['subnetId'] = subnet_id
            self._state['allocationId'] = allocation_id
            self._state['natGatewayId'] = gtw_id

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting vpc NAT gateway {}".format(self._state['natGatewayId']))
        self.connect()
        try:
            self._client.delete_nat_gateway(NatGatewayId=self._state['natGatewayId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidNatGatewayID.NotFound":
                self.warn("nat gateway {} was already deleted".format(self._state['natGatewayId']))
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['subnetId'] = None
            self._state['allocationId'] = None
            self._state['natGatewayId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
