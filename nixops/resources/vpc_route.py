# -*- coding: utf-8 -*-

# Automatic provisioning of AWS VPC route.

import boto3
import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class VPCRouteDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPC route"""

    @classmethod
    def get_type(cls):
        return "vpc-route"

    @classmethod
    def get_resource_type(cls):
        return "vpcRoutes"

    def show_type(self):
        return "{0}".format(self.get_type())

class VPCRouteState(nixops.resources.ResourceState, EC2CommonState):
    """State of a VPC route"""

    state = nixops.util.attr_property("state", nixops.resources.ResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED
    TARGETS = ['gatewayId', 'instanceId', 'natGatewayId', 'networkInterfaceId']

    @classmethod
    def get_type(cls):
        return "vpc-route"

    def __init__(self, depl, name, id):
        nixops.resources.ResourceState.__init__(self, depl, name, id)
        self._client = None
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        keys = ['region', 'routeTableId', 'destinationCidrBlock', 'destinationIpv6CidrBlock',
                'gatewayId', 'instanceId', 'natGatewayId', 'networkInterfaceId']
        self.handle_create_route = Handler(keys, handle=self.realize_create_route)

    def show_type(self):
        s = super(VPCRouteState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return (self._state.get('destinationCidrBlock', None) or self._state.get('destinationIpv6CidrBlock', None))

    def prefix_definition(self, attr):
        return {('resources', 'vpcRoutes'): attr}

    def get_definition_prefix(self):
        return "resources.vpcRoutes."

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

    def realize_create_route(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("route {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self.name))
            self.warn("route definition changed, recreating ...")
            self._destroy()
            self._client = None

        self._state['region'] = config['region']
        self.connect()

        rtb_id = config['routeTableId']
        if rtb_id.startswith("res-"):
            res = self.depl.get_typed_resource(rtb_id[4:].split(".")[0], "vpc-route-table")
            rtb_id = res._state['routeTableId']

        route = dict()
        config = self.get_defn()
        num_targets = 0
        for item in self.TARGETS:
            if config[item]:
                num_targets+=1
                target = item

        if num_targets > 1:
            raise Exception("you should specify only 1 target from {}".format(str(self.TARGETS)))

        if (config['destinationCidrBlock'] is not None) and (config['destinationIpv6CidrBlock'] is not None):
            raise Exception("you can't set both destinationCidrBlock and destinationIpv6CidrBlock in one route")

        if config['destinationCidrBlock'] is not None: destination = 'destinationCidrBlock'
        if config['destinationIpv6CidrBlock'] is not None: destination = 'destinationIpv6CidrBlock'

        def retrieve_defn(option):
            cfg = config[option]
            if cfg.startswith("res-"):
                name = cfg[4:].split(".")[0]
                res_type = cfg.split(".")[1]
                attr = cfg.split(".")[2] if len(cfg.split(".")) > 2 else option
                res = self.depl.get_typed_resource(name, res_type)
                return res._state[attr]
            else:
                return cfg

        route['RouteTableId'] = rtb_id
        route[self.upper(target)] = retrieve_defn(target)
        route[self.upper(destination)] = config[destination]

        self.log("creating route {0} => {1} in route table {2}".format(retrieve_defn(target), config[destination], rtb_id))
        self._client.create_route(**route)

        with self.depl._db:
            self.state = self.UP
            self._state[target] = route[self.upper(target)]
            self._state[destination] = config[destination]
            self._state['routeTableId'] = rtb_id

    def upper(self, option):
        return "%s%s" % (option[0].upper(), option[1:])

    def _destroy(self):
        if self.state != self.UP: return
        destination = 'destinationCidrBlock' if ('destinationCidrBlock' in self._state.keys()) else 'destinationIpv6CidrBlock'
        self.log("deleting route to {0} from route table {1}".format(self._state[destination], self._state['routeTableId']))
        self.connect()
        try:
            args = dict()
            args[self.upper(destination)] = self._state[destination]
            args['RouteTableId'] = self._state['routeTableId']
            self._client.delete_route(**args)
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == "InvalidRoute.NotFound":
                self.warn("route was already deleted")
            else:
                raise error

        with self.depl._db:
            self.state = self.MISSING
            self._state['routeTableId'] = None
            self._state[destination] = None
            for target in self.TARGETS:
                self._state[target] = None

    def destroy(self, wipe=False):
        self._destroy()
        return True
