# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC NAT gateways.

import uuid
import time

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
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

class VPCNatGatewayState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC NAT gateway"""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['natGatewayId', 'creationToken']

    @classmethod
    def get_type(cls):
        return "vpc-nat-gateway"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_gtw = Handler(['region', 'subnetId', 'allocationId'], handle=self.realize_create_gtw)
        self.nat_gtw_id = self._state.get('natGatewayId', None)

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

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState) or
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)
        change_sequence = diff_engine.plan()

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in change_sequence:
            handler.handle(allow_recreate)

    def realize_create_gtw(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("nat gateway {} defintion changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['natGatewayId']))
            self.warn("nat gateway changed, recreating...")
            self._destroy()

        self._state['region'] = config['region']

        subnet_id = config['subnetId']
        allocation_id = config['allocationId']

        if allocation_id.startswith("res-"):
            res = self.depl.get_typed_resource(allocation_id[4:].split(".")[0], "elastic-ip")
            allocation_id = res.allocation_id

        if subnet_id.startswith("res-"):
            res = self.depl.get_typed_resource(subnet_id[4:].split(".")[0], "vpc-subnet")
            subnet_id = res._state['subnetId']

        if not self._state.get('creationToken', None):
            self._state['creationToken'] = str(uuid.uuid4())
            self.state = self.STARTING

        response = self.get_client().create_nat_gateway(ClientToken=self._state['creationToken'], AllocationId=allocation_id,
                                                   SubnetId=subnet_id)

        gtw_id = response['NatGateway']['NatGatewayId']
        with self.depl._db:
            self.state = self.UP
            self._state['subnetId'] = subnet_id
            self._state['allocationId'] = allocation_id
            self._state['natGatewayId'] = gtw_id

    def wait_for_nat_gtw_deletion(self):
        self.log("waiting for nat gateway {0} to be deleted".format(self._state['natGatewayId']))
        while True:
            try:
                response = self.get_client().describe_nat_gateways(
                    NatGatewayIds=[self._state['natGatewayId']]
                    )
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "InvalidNatGatewayID.NotFound" or e.response['Error']['Code'] == "NatGatewayNotFound":
                    self.warn("nat gateway {} was already deleted".format(self._state['natGatewayId']))
                    break
                else:
                    raise
            if len(response['NatGateways'])==1:
                if response['NatGateways'][0]['State'] == "deleted":
                    break
                elif response['NatGateways'][0]['State'] != "deleting":
                    raise Exception("nat gateway {0} in an unexpected state {1}".format(
                        self._state['natGatewayId'], response['NatGateways'][0]['State']))
                self.log_continue(".")
                time.sleep(1)
            else:
                break
        self.log_end(" done")

    def _destroy(self):
        if self.state == self.UP:
            self.log("deleting vpc NAT gateway {}".format(self._state['natGatewayId']))
            try:
                self.get_client().delete_nat_gateway(NatGatewayId=self._state['natGatewayId'])
                with self.depl._db: self.state = self.STOPPING
            except botocore.exceptions.ClientError as e:
                if e.response['Error']['Code'] == "InvalidNatGatewayID.NotFound" or e.response['Error']['Code'] == "NatGatewayNotFound":
                    self.warn("nat gateway {} was already deleted".format(self._state['natGatewayId']))
                else:
                    raise e

        if self.state == self.STOPPING:
            self.wait_for_nat_gtw_deletion()

        with self.depl._db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['subnetId'] = None
            self._state['allocationId'] = None
            self._state['natGatewayId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
