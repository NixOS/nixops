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


class VPCEgressOnlyInternetGatewayState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC egress only internet gateway."""
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["egressOnlyInternetGatewayId"]

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self._client = None
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
                raise Exception("egress only internet gateway {} defintion changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['egressOnlyInternetGatewayId']))
            self.warn("egress only internet gateway changed, recreating...")
            self._destroy()
            self._client = None

        self._state['region'] = config['region']

        self.connect()

        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating egress only internet gateway in region {0}, vpc {1}".format(self._state['region'], vpc_id))
        response = self._client.create_egress_only_internet_gateway(VpcId=vpc_id)
        igw_id = response['EgressOnlyInternetGateway']['EgressOnlyInternetGatewayId']

        with self.depl._db:
            self.state = self.UP
            self._state['region'] = config['region']
            self._state['vpcId'] = vpc_id
            self._state['egressOnlyInternetGatewayId'] = igw_id

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        self.log("deleting egress only internet gateway {0}".format(self._state['egressOnlyInternetGatewayId']))
        self._client.delete_egress_only_internet_gateway(EgressOnlyInternetGatewayId=self._state['egressOnlyInternetGatewayId'])

        with self.depl._db:
            self.state = self.MISSING
            self._state['region'] = None
            self._state['vpcId'] = None
            self._state['egressOnlyInternetGatewayId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True