# -*- coding: utf-8 -*-

import botocore

import nixops.util
import nixops.resources
from nixops.resources.ec2_common import EC2CommonState
import nixops.ec2_utils
from nixops.diff import Diff, Handler
from nixops.state import StateDict

class AWSVPNConnectionRouteDefinition(nixops.resources.ResourceDefinition):
    """Definition of a VPN connection route"""

    @classmethod
    def get_type(cls):
        return "aws-vpn-connection-route"

    @classmethod
    def get_resource_type(cls):
        return "awsVPNConnectionRoutes"

    def show_type(self):
        return "{0}".format(self.get_type())

class AWSVPNConnectionState(nixops.resources.DiffEngineResourceState, EC2CommonState):
    """State of a VPN connection route"""

    state = nixops.util.attr_property("state", nixops.resources.DiffEngineResourceState.MISSING, int)
    access_key_id = nixops.util.attr_property("accessKeyId", None)
    _reserved_keys = EC2CommonState.COMMON_EC2_RESERVED

    @classmethod
    def get_type(cls):
        return "aws-vpn-connection-route"

    def __init__(self, depl, name, id):
        nixops.resources.DiffEngineResourceState.__init__(self, depl, name, id)
        self._state = StateDict(depl, id)
        self.region = self._state.get('region', None)
        self.handle_create_vpn_route = Handler(['region', 'vpnConnectionId', 'destinationCidrBlock'], handle=self.realize_create_vpn_route)

    def show_type(self):
        s = super(AWSVPNConnectionState, self).show_type()
        if self.region: s = "{0} [{1}]".format(s, self.region)
        return s

    @property
    def resource_id(self):
        return self._state.get('destinationCidrBlock', None)

    def prefix_definition(self, attr):
        return {('resources', 'awsVPNConnectionRoutes'): attr}

    def get_definition_prefix(self):
        return "resources.awsVPNConnectionRoutes."

    def create_after(self, resources, defn):
        return {r for r in resources if
                isinstance(r, nixops.resources.aws_vpn_connection.AWSVPNConnectionState)}

    def create(self, defn, check, allow_reboot, allow_recreate):
        diff_engine = self.setup_diff_engine(config=defn.config)

        self.access_key_id = defn.config['accessKeyId'] or nixops.ec2_utils.get_access_key_id()
        if not self.access_key_id:
            raise Exception("please set 'accessKeyId', $EC2_ACCESS_KEY or $AWS_ACCESS_KEY_ID")

        for handler in diff_engine.plan():
            handler.handle(allow_recreate)

    def realize_create_vpn_route(self, allow_recreate):
        config = self.get_defn()

        if self.state == self.UP:
            if not allow_recreate:
                raise Exception("vpn connection route {} definition changed and it needs to be recreated"
                                " use --allow-recreate if you want to create a new one".format(self.name))
            self.warn("route definition changed, recreating ...")
            self._destroy()

        self._state['region'] = config['region']
        vpn_conn_id = config['vpnConnectionId']
        if vpn_conn_id.startswith("res-"):
            res = self.depl.get_typed_resource(vpn_conn_id[4:].split(".")[0], "aws-vpn-connection")
            vpn_conn_id = res._state['vpnConnectionId']

        self.log("creating route to {0} using vpn connection {1}".format(config['destinationCidrBlock'], vpn_conn_id))
        self.get_client().create_vpn_connection_route(
            DestinationCidrBlock=config['destinationCidrBlock'],
            VpnConnectionId=vpn_conn_id)

        with self.depl._db:
            self.state = self.UP
            self._state['vpnConnectionId'] = vpn_conn_id
            self._state['destinationCidrBlock'] = config['destinationCidrBlock']

    def _destroy(self):
        if self.state != self.UP: return
        self.log("deleting route to {}".format(self._state['destinationCidrBlock']))
        try:
            self.get_client().delete_vpn_connection_route(
                DestinationCidrBlock=self._state['destinationCidrBlock'],
                VpnConnectionId=self._state['vpnConnectionId'])
        except botocore.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "InvalidRoute.NotFound" or e.response['Error']['Code'] == "InvalidVpnConnectionID.NotFound":
                self.warn("route or vpn connection was already deleted")
            else:
                raise e

        with self.depl._db:
            self.state = self.MISSING
            self._state['vpnConnectionId'] = None
            self._state['destinationCidrBlock'] = None

    def destroy(self, wipe=True):
        self._destroy()
        return True
