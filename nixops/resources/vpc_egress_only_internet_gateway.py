# -*- coding: utf-8 -*-

import boto3
import botocore

from nixops.state import StateDict
from nixops.diff import Diff, Handler
import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils

class VPCEgressOnlyInternetGatewayDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC egress only internet gateway."""

    @classmethod
    def get_type(cls):
        return "vpc-egress-only-internet-gateway"

    @classmethod
    def get_resource_type(cls):
        return "vpcEgressOnlyInternetGateways"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCEgressOnlyInternetGatewayState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC egress only internet gateway."""
    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["egressOnlyInternetGatewayId"]

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.handle_create_igw = Handler(['region', 'vpcId'], handle=self.realize_create_gtw)

    @classmethod
    def get_type(cls):
        return "vpc-egress-only-internet-gateway"

    def show_type(self):
        s = super(VPCEgressOnlyInternetGatewayState, self).show_type()
        if self._state.get('region', None): s = "{0} [{1}]".format(s, self._state['region'])
        return s

    @property
    def resource_id(self):
        return self._state.get('egressOnlyInternetGatewayId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcEgressOnlyInternetGateways'): attr}

    def get_defintion_prefix(self):
        return "resources.vpcEgressOnlyInternetGateways."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.elastic_ip.ElasticIPState)}

    def realize_create_gtw(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("egress only internet gateway {} defintion changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['egressOnlyInternetGatewayId']))
            self.warn("egress only internet gateway changed, recreating...")
            self._destroy()

        self._state['region'] = config['region']

        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating egress only internet gateway in region {0}, vpc {1}".format(self._state['region'], vpc_id))
        response = self.get_client().create_egress_only_internet_gateway(VpcId=vpc_id)
        igw_id = response['EgressOnlyInternetGateway']['EgressOnlyInternetGatewayId']

        with self.depl._state.db:
            self.state = self.UP
            self._state['region'] = config['region']
            self._state['vpcId'] = vpc_id
            self._state['egressOnlyInternetGatewayId'] = igw_id

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting egress only internet gateway {0}".format(self._state['egressOnlyInternetGatewayId']))
        self.get_client().delete_egress_only_internet_gateway(EgressOnlyInternetGatewayId=self._state['egressOnlyInternetGatewayId'])

        with self.depl._state.db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['vpcId'] = None
            self._state['egressOnlyInternetGatewayId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
