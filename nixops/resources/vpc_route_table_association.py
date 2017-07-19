# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC route table association.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCRouteTableAssociationDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC route table association"""

    @classmethod
    def get_type(cls):
        return "vpc-route-table-association"

    @classmethod
    def get_resource_type(cls):
        return "vpcRouteTableAssociations"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCRouteTableAssociationState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC route table association"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ['associationId']

    @classmethod
    def get_type(cls):
        return "vpc-route-table-association"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_associate_route_table = Handler(['region', 'routeTableId', 'subnetId'], handle=self.realize_associate_route_table)

    def show_type(self):
        s = super(VPCRouteTableAssociationState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('associationId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcRouteTableAssociations'): attr}

    def get_physical_spec(self):
        return { 'associationId': self._state.get('associationId', None) }

    def get_definition_prefix(self):
        return "resources.vpcRouteTableAssociations."

    def connect(self):
        if self._client: return
        self._client = nixops.ec2_utils.connect_ec2_boto3(self._state['region'], self.access_key_id)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc_route_table.VPCRouteTableState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

    def realize_associate_route_table(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("route table association {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self._state['associationId']))
            self.warn("route table association definition changed, recreating ...")
            self._destroy()
            self._client = None

        self._state['region'] = config['region']
        self.connect()

        route_table_id = config['routeTableId']
        if route_table_id.startswith("res-"):
            res = self.depl.get_typed_resource(route_table_id[4:].split(".")[0], "vpc-route-table")
            route_table_id = res._state['routeTableId']

        subnet_id = config['subnetId']
        if subnet_id.startswith("res-"):
            res = self.depl.get_typed_resource(subnet_id[4:].split(".")[0], "vpc-subnet")
            subnet_id = res._state['subnetId']

        self.log("associating route table {0} to subnet {1}".format(route_table_id, subnet_id))
        association = self._client.associate_route_table(RouteTableId=route_table_id,
                                                         SubnetId=subnet_id)

        with self.depl._db:
            self.state = self.UP
            self._state['routeTableId'] = route_table_id
            self._state['subnetId'] = subnet_id
            self._state['associationId'] = association['AssociationId']

    def _destroy(self):
        if self.state != self.UP: return
        self.log("disassociating route table {0} from subnet {1}".format(self._state['routeTableId'], self._state['subnetId']))
        self.connect()
        try:
            self._client.disassociate_route_table(AssociationId=self._state['associationId'])
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidAssociationID.NotFound":
                self.warn("route table {} was already deleted".format(self._state['associationId']))
            else:
                raise error

        with self.depl._db:
            self.state = self.MISSING
            self._state['routeTableId'] = None
            self._state['subnetId'] = None
            self._state['associationId'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
