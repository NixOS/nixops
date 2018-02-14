# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC route tables.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state.state import StateDict

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

class VPCRouteTableState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPC route table"""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['routeTableId']

    @classmethod
    def get_type(cls):
        return "vpc-route-table"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_route_table = Handler(['region', 'vpcId'], handle=self.realize_create_route_table)
        self.handle_propagate_vpn_gtws = Handler(
            ['propagatingVgws'],
            handle=self.realize_propagate_vpn_gtws,
            after=[self.handle_create_route_table])
        self.handle_tag_update = Handler(['tags'], after=[self.handle_create_route_table], handle=self.realize_update_tag)

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

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.vpc_subnet.VPCSubnetState)}

    def realize_create_route_table(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("route table {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self._state['routeTableId']))
            self.warn("route table definition changed, recreating ...")
            self._destroy()

        self._state['region'] = config['region']

        vpc_id = config['vpcId']
        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state['vpcId']

        self.log("creating route table in vpc {}".format(vpc_id))
        route_table = self.get_client().create_route_table(VpcId=vpc_id)

        with self.depl._state.db:
            self.state = self.UP
            self._state['vpcId'] = vpc_id
            self._state['routeTableId'] = route_table['RouteTable']['RouteTableId']

    def realize_propagate_vpn_gtws(self, allow_recreate):
        config = self.get_defn()
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
            self.get_client().disable_vgw_route_propagation(
                GatewayId=vgw,
                RouteTableId=self._state['routeTableId'])
        for vgw in to_enable:
            self.log("enabling virtual gateway route propagation for {}".format(vgw))
            self.get_client().enable_vgw_route_propagation(
                GatewayId=vgw,
                RouteTableId=self._state['routeTableId'])

        with self.depl._state.db:
            self._state['propagatingVgws'] = new_vgws

    def realize_update_tag(self, allow_recreate):
        config = self.get_defn()
        tags = config['tags']
        tags.update(self.get_common_tags())
        self.get_client().create_tags(Resources=[self._state['routeTableId']], Tags=[{"Key": k, "Value": tags[k]} for k in tags])

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting route table {}".format(self._state['routeTableId']))
        try:
            self.get_client().delete_route_table(RouteTableId=self._state['routeTableId'])
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidRouteTableID.NotFound":
                self.warn("route table {} was already deleted".format(self._state['routeTableId']))
            else:
                raise error

        with self.depl._state.db:
            self.state = self.MISSING
            self._state['vpcId'] = None
            self._state['routeTableId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
