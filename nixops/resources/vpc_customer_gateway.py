# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC customer gateways.

import os

import boto3
import botocore

from nixops.state.state_helper import StateDict
from nixops.diff import Diff, Handler
import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils

class VPCCustomerGatewayDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC customer gateway."""

    @classmethod
    def get_type(cls):
        return "vpc-customer-gateway"

    @classmethod
    def get_resource_type(cls):
        return "vpcCustomerGateways"

    def show_type(self):
        return "{0}".format(self.get_type())


class VPCCustomerGatewayState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC customer gateway."""
    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["customerGatewayId"]

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.handle_create_customer_gtw = Handler(['region', 'publicIp', 'bgpAsn', 'type'], handle=self.realize_create_customer_gtw)
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_customer_gtw], handle=self.realize_update_tag)

    @classmethod
    def get_type(cls):
        return "vpc-customer-gateway"

    def show_type(self):
        s = super(VPCCustomerGatewayState, self).show_type()
        if self._state.get('region', None): s = "{0} [{1}]".format(s, self._state['region'])
        return s

    @property
    def resource_id(self):
        return self._state.get('customerGatewayId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcCustomerGateways'): attr}

    def get_defintion_prefix(self):
        return "resources.vpcCustomerGateways."

    def realize_create_customer_gtw(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("customer gateway {} defintion changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['customerGatewayId']))
            self.warn("customer gateway changed, recreating...")
            self._destroy()

        self._state['region'] = config['region']

        self.log("creating customer gateway")
        response = self.get_client().create_customer_gateway(
            BgpAsn=config['bgpAsn'],
            PublicIp=config['publicIp'],
            Type=config['type'])

        customer_gtw_id = response['CustomerGateway']['CustomerGatewayId']
        with self.depl._state.db: self.state = self.STARTING

        waiter = self.get_client().get_waiter('customer_gateway_available')
        waiter.wait(CustomerGatewayIds=[customer_gtw_id])

        with self.depl._state.db:
            self.state = self.UP
            self._state['region'] = config['region']
            self._state['customerGatewayId'] = customer_gtw_id
            self._state['bgpAsn'] = config['bgpAsn']
            self._state['publicIp'] = config['publicIp']
            self._state['type'] = config['type']

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['customerGatewayId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting customer gateway {}".format(self._state['customerGatewayId']))
        try:
            self.get_client().delete_customer_gateway(CustomerGatewayId=self._state['customerGatewayId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidCustomerGatewayID.NotFound":
                self.warn("customer gateway {} was already deleted".format(self._state['customerGatewayId']))
            else:
                raise e

        #TODO wait for customer gtw to be deleted
        with self.depl._state.db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['customerGatewayId'] = None
            self._state['bgpAsn'] = None
            self._state['publicIp'] = None
            self._state['type'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
