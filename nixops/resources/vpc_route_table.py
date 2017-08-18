# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC route tables.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCRouteTableDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC route table"""

    @classmethod
    def get_type(cls):
        return "vpc-route-table"

    @classmethod
    def get_resource_type(cls):
        return "vpcRouteTables"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCRouteTableState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC route table"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['routeTableId']

    @classmethod
    def get_type(cls):
        return "vpc-route-table"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_route_table = Handler(['region', 'vpcId'], handle=self.realize_create_route_table)
        self.handle_propagate_vpn_gtws = Handler(
            ['propagatingVgws'],
            handle=self.realize_propagate_vpn_gtws,
            after=[self.handle_create_route_table])

    def show_type(self):
        s = super(VPCRouteTableState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('routeTableId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcRouteTables'): attr}

    def get_physical_spec(self):
        return { 'routeTableId': self._state.get('routeTableId', None) }

    def get_definition_prefix(self):
        return "resources.vpcRouteTables."

    def connect(self):
        if self._client: return
        self._client = nixops.ec2_utils.connect_ec2_boto3(self._state['region'], self.access_key_id)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

    def realize_create_route_table(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("route table {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self._state['routeTableId']))
            self.warn("route table definition changed, recreating ...")
            self._destroy()
            self._client = None

        self._state['region'] = config['region']
        self.connect()

        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating route table in vpc {}".format(vpc_id))
        route_table = self._client.create_route_table(VpcId=vpc_id)

        with self.depl._db:
            self.state = self.UP
            self._state['vpcId'] = vpc_id
            self._state['routeTableId'] = route_table['RouteTable']['RouteTableId']

    def realize_propagate_vpn_gtws(self, allow_recreate):
        config = self.get_defn()

        self.connect()

        old_vgws = self._state.get('propagatingVgws', [])
        new_vgws = []

        for vgw in config['propagatingVgws']:
            if vgw.startswith("res-"):
                res = self.depl.get_typed_resource(vgw[4:].split(".")[0], "aws-vpn-gateway")
                new_vgws.append(res._state['vpnGatewayId'])
            else:
                new_vgws.append(vgw)

        to_disable = [r for r in old_vgws if r not in new_vgws]
        to_enable = [r for r in new_vgws if r not in old_vgws]

        for vgw in to_disable:
            self.log("disabling virtual gateway route propagation for {}".format(vgw))
            self._client.disable_vgw_route_propagation(
                GatewayId=vgw,
                RouteTableId=self._state['routeTableId'])
        for vgw in to_enable:
            self.log("enabling virtual gateway route propagation for {}".format(vgw))
            self._client.enable_vgw_route_propagation(
                GatewayId=vgw,
                RouteTableId=self._state['routeTableId'])

        with self.depl._db:
            self._state['propagatingVgws'] = new_vgws

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting route table {}".format(self._state['routeTableId']))
        self.connect()
        try:
            self._client.delete_route_table(RouteTableId=self._state['routeTableId'])
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidRouteTableID.NotFound":
                self.warn("route table {} was already deleted".format(self._state['routeTableId']))
            else:
                raise error

        with self.depl._db:
            self.state = self.MISSING
            self._state['vpcId'] = None
            self._state['routeTableId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
