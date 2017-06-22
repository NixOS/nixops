# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC NAT gateways.

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
    handle_create_gtw = Handler(['region', 'subnetId'])

    @classmethod
    def get_type(cls):
        return "vpc-nat-gateway"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self._config = depl.definitions[name]
        self.region = self._state.get('region', None)
        self.handle_create_gtw.handle = self.realize_create_gtw

    def show_type(self):
        s = super(VPCNatGatewayState, self).show_type()
        if self.region: s = "{0} [${1}]".format(s, self.region)
        return s

    def get_handlers(self):
        return [getattr(self,h) for h in dir(self) if isinstance(getattr(self,h), Handler)]

    @property
    def resource_id(self):
        return self._state.get('natGatewayId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcNatGateways'): attr}

    def get_physical_spec(self):
        return { 'natGatewayId': self._state.get('natGatewayId', None) }

    def get_definition_prefix(self):
        return "resources.vpcSubnets."

