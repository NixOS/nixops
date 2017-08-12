# -*- coding: utf-8 -*-

import uuid

from nixops.state import StateDict
from nixops.diff import Diff, Handler
import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils

class VPCEndpointDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC endpoint."""

    @classmethod
    def get_type(cls):
        return "vpc-endpoint"

    @classmethod
    def get_resource_type(cls):
        return "vpcEndpoints"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCEndpointState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC endpoint."""
    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED + ["endpointId","creationToken"]

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self._client = None
        self.handle_create_endpoint = Handler(['region', 'serviceName', 'vpcId'], handle=self.realize_create_endpoint)
        self.handle_modify_endpoint = Handler(['policy', 'routeTableIds'],
                after=[self.handle_create_endpoint],
                handle=self.realize_modify_endpoint)

    @classmethod
    def get_type(cls):
        return "vpc-endpoint"

    def show_type(self):
        s = super(VPCEndpointState, self).show_type()
        if self._state.get('region', None): s = "{0} [{1}]".format(s, self._state['region'])
        return s

    @property
    def resource_id(self):
        return self._state.get('endpointId', None)

    def prefix_definition(self, attr):
        return {('resources', 'vpcEndpoints'): attr}

    def get_defintion_prefix(self):
        return "resources.vpcEndpoints"

    def connect(self):
        if self._client: return
        self._client = nixops.ec2_utils.connect_ec2_boto3(self._state['region'], self.access_key_id)

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.vpc.VPCState) or
                isinstance(r, nixops.resources.vpc_route_table.VPCRouteTableState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)
        change_sequence = diff_engine.plan()

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in change_sequence:
            handler.handle(allow_recreate)

    def realize_create_endpoint(self, allow_recreate):
        config = self.get_defn()
        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("vpc endpoint {} definition changed"
                                " use --allow-recreate if you want to create a new one".format(
                                    self._state['endpointId']))
            self.warn("vpc endpoint changed, recreating...")
            self._destroy()
            self._client = None

        self._state['region'] = config['region']
        self.connect()

        vpc_id = config['vpcId']

        if vpc_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpc_id[4:].split(".")[0], "vpc")
            vpc_id = res._state["vpcId"]

        if not self._state.get('creationToken', None):
            self._state['creationToken'] = str(uuid.uuid4())
            self.state = self.STARTING

        response = self._client.create_vpc_endpoint(
            ClientToken=self._state['creationToken'],
            ServiceName=config['serviceName'],
            VpcId=vpc_id)

        endpoint_id = response['VpcEndpoint']['VpcEndpointId']
        with self.depl._db:
            self.state = self.UP
            self._state['endpointId'] = endpoint_id
            self._state['vpcId'] = vpc_id
            self._state['serviceName'] = config['serviceName']

    def realize_modify_endpoint(self, allow_recreate):
        config = self.get_defn()
        self.connect()
        old_rtbs = self._state.get('routeTableIds', [])
        new_rtbs = []
        for rtb in config["routeTableIds"]:
            if rtb.startswith("res-"):
               res = self.depl.get_typed_resource(rtb[4:].split(".")[0], "vpc-route-table")
               new_rtbs.append(res._state['routeTableId'])
            else:
               new_rtbs.append(rtb)

        to_remove = [r for r in old_rtbs if r not in new_rtbs]
        to_add = [r for r in new_rtbs if r not in old_rtbs]

        edp_input = dict()
        edp_input['AddRouteTableIds'] = to_add
        edp_input['RemoveRouteTableIds'] = to_remove
        if config['policy'] is not None: edp_input['PolicyDocument']
        edp_input['VpcEndpointId'] = self._state['endpointId']

        print edp_input
        self._client.modify_vpc_endpoint(**edp_input)

        with self.depl._db:
            self._state['policy'] = config['policy']
            self._state['routeTableIds'] = new_rtbs

    def _destroy(self):
        if self.state != self.UP: return
        self.connect()
        try:
            self.log("deleting vpc endpoint {}".format(self._state['endpointId']))
            self._client.delete_vpc_endpoints(VpcEndpointIds=[self._state['endpointId']])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'InvalidVpcEndpointId.NotFound':
                self.warn("vpc endpoint {} was already deleted".format(self._state['endpointId']))
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self._state['endpointId'] = None
            self._state['vpcId'] = None
            self._state['serviceName'] = None
            self._state['policy'] = None
            self._state['routeTableIds'] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
